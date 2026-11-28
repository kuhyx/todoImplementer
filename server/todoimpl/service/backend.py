"""The http Backend over the real pieces: cached todo notes, run states, the Scheduler, usage, lessons."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.apikey.keystatus import board_field
from todoimpl.board.board import build_board, build_task, repo_checker
from todoimpl.board.card import Context
from todoimpl.board.diff import worktree_diff
from todoimpl.board.outrank import backlog, mark
from todoimpl.board.state import load, load_runs, run_dir
from todoimpl.board.types import Credits, Limit
from todoimpl.credits import marks, route
from todoimpl.http.backend import ERROR_CODES, BackendError
from todoimpl.lessons import LessonError, approve, draft_lesson, latest_lesson, run_skills
from todoimpl.repotask.files import overlay as ticks_overlay
from todoimpl.runner import autocheck, modelswitch, prepin
from todoimpl.runner.scheduler import RunnerError
from todoimpl.stall.scan import card_activity
from todoimpl.todo_mcp.model import TodoError, upstream_text
from todoimpl.umbrella.view import overlay_for
from todoimpl.usage import hold, limit_state
from todoimpl.usage.interventions import record

from . import dropping, livefeed, notes, permission, priorities, shots, tracking
from .settings import credits_fallback as _credits_fallback

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.apikey.monitor import KeyMonitor
    from todoimpl.asks.service import AskService
    from todoimpl.board.state import RunState
    from todoimpl.gateway.monitor import GatewayMonitor
    from todoimpl.merge.service import MergeService
    from todoimpl.newtask.service import NewTaskService
    from todoimpl.nolimit.tick import Loop as NoLimitLoop
    from todoimpl.runner.limitprobe import LimitProbe
    from todoimpl.triage.service import TriageService

    from .cache import TaskCache
    from .scheduling import SchedulerLike

log = logging.getLogger("todoimpl.service")
UPSTREAM, CONFLICT = "upstream_unavailable", "conflict"


def _spawn(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="lesson-draft", daemon=True).start()


class ServiceBackend:
    """Implements todoimpl.http.backend.Backend; every read is served from memory and small files."""

    def __init__(  # noqa: PLR0913 - the collaborators; all injectable for tests
        self,
        cache: TaskCache,
        scheduler: SchedulerLike,
        root: Path,
        build: str,
        *,
        clock: Callable[[], float] = time.time,
        drafter: Callable[[str], str] | None = None,
        spawn: Callable[[Callable[[], None]], None] = _spawn,
        repo_missing: Callable[[str | None], str | None] | None = None,
        fix_runner: Callable[[str], tuple[int, str]] = permission.run_command,
        key_monitor: KeyMonitor | None = None,
        limit_probe: LimitProbe | None = None,
        gateway: GatewayMonitor | None = None,
    ) -> None:
        """Wire the pieces; nothing is read until a request arrives."""
        self.cache = cache
        self.scheduler = scheduler
        self.root, self.build = root, build
        self._clock = clock
        self.drafter = drafter  # lesson drafter; None = the real `claude -p` one
        self.spawn = spawn  # runs a background job; tests run it inline
        self._repo_missing = repo_missing or repo_checker()
        self.fix_runner = fix_runner  # runs a permission block's one-liner; tests inject a fake
        self.key_monitor = key_monitor  # the API key's newest status rides on the board
        self.limit_probe = limit_probe  # re-checks a stored plan limit against the plan's real usage
        self.gateway = gateway  # the free-model gateway's newest reading rides on /api/usage
        self.merge_service: MergeService | None = None  # set by build_backend; the http layer looks for it
        self.ask_service: AskService | None = None  # POST /api/task/<id>/ask/<verb>
        self.part_service: object = None  # POST /api/task/<id>/part-edit (service/partedit.py)
        self.new_task_service: NewTaskService | None = None  # POST /api/new-task
        self.triage_service: TriageService | None = None  # labels repo-less notes (DOCS-triage.md)
        self.known_repos: Callable[[], list[str]] = list  # GitHub repos beside the cards' (T2413)
        self.peer_hub: object = None  # todoimpl.peer.hub.Hub, set by build_backend (DOCS-peer.md)
        self.nolimit: NoLimitLoop | None = None  # tokenless repo upkeep (DOCS-nolimit.md)

    def _context(self) -> Context:
        now = self._clock()
        state = limit_state(self.root)  # read first: a fast probe must not change this response mid-build
        active = state.active(now)
        if self.limit_probe is not None:
            self.limit_probe.refresh_if_due()  # a page load re-checks a held limit in the background
        return Context(
            live=frozenset(self.scheduler.running()),
            limit=Limit(
                active,
                state.until if active else None,
                Credits(**route.view(self.root, now)),
                hold.level(self.root, now),
                hold.used(self.root, now),
                hold.allowance(self.root, now),
            ),
            now=now,
            repo_missing=self._repo_missing,
            auto_close=autocheck.enabled(self.root),
            checks=autocheck.load_cache(self.root),
            waits=dict(getattr(self.scheduler, "lock_waits", dict)()),
            activity=partial(card_activity, self.root),
            pin=partial(prepin.read_card, self.root),
            creating=self.triage_service.busy() if self.triage_service is not None else frozenset(),
        )

    def _with_extras(self, run: RunState | None) -> RunState | None:
        """Overlay the drafted lesson and the skills seen in the streams; they live outside state.json."""
        if run is None:
            return None
        directory = run_dir(self.root, run.task_id)
        run = modelswitch.overlay(directory, run)  # a pick a live drive has not settled yet
        try:
            latest = latest_lesson(directory)
        except LessonError as exc:  # a corrupt lessons.json must not take the whole board down
            return replace(run, error=run.error or str(exc))
        lesson, skills = (latest.to_dict() if latest else run.lesson), run_skills(directory)
        found = replace(run, lesson=lesson, skills_loaded=skills or run.skills_loaded)
        return overlay_for(self._context, directory, ticks_overlay(directory, found))

    def board(self) -> dict[str, Any]:
        """GET /api/board."""
        snap = self.cache.snapshot()
        if snap.error and not snap.loaded:  # no board ever existed: nothing honest to show but the error
            raise BackendError(UPSTREAM, upstream_text(snap.error))
        tasks = snap.tasks
        runs = load_runs(self.root, [t.id for t in tasks])
        extended = {key: self._with_extras(run) for key, run in runs.items()}
        board = build_board(tasks, extended, self._context(), self.build, self.known_repos())  # type: ignore[arg-type]
        if snap.error:  # stale cards plus a banner, never an empty board that looks healthy
            board["error"] = {"code": UPSTREAM, "message": upstream_text(snap.error)}
        if (alert := marks.active_alert(self.root, self._clock())) is not None:
            board["alert"] = alert
        latest = self.key_monitor.latest() if self.key_monitor else None
        if latest is not None:  # before the first check there is nothing honest to say
            board["api_key"] = board_field(latest)
        return board

    def task(self, id8: str) -> dict[str, Any] | None:
        """GET /api/task/<id8>."""
        found = next((t for t in self.cache.snapshot().tasks if t.id == id8), None)
        if found is None:
            return None
        run = self._with_extras(load(run_dir(self.root, id8)))
        diff = worktree_diff(run.worktree, run.base_sha) if run is not None else None
        detail = build_task(found, run, run_dir(self.root, id8), self._context(), diff)
        tasks = self.cache.snapshot().tasks  # Start asks first while a higher card waits (T2583)
        mark(detail["card"], backlog(tasks, dict(load_runs(self.root, [t.id for t in tasks]))))
        return detail

    def shot(self, id8: str, name: str) -> bytes | None:
        """Bytes of the png at `name` (a/b.png) under `<run dir>/shots`; None when it resolves outside it."""
        return shots.read_shot(run_dir(self.root, id8), name)

    issues = tracking.issues  # GET /api/task/<id8>/issues; these four need only the cache, run dirs, gateway
    usage = tracking.usage  # GET /api/usage
    umbrella = tracking.umbrella  # GET /api/umbrella/<id8>
    worker_log = tracking.worker_log  # the tail of a child's newest worker log
    wont = dropping.wont  # Won't do click (T2045)
    done_manually = dropping.done_manually  # Done manually click (T2064)
    priority = priorities.set_priority  # Priority pick (T2583)
    set_credits_fallback = _credits_fallback  # POST /api/settings/credits-fallback

    subscribe = livefeed.subscribe  # GET /api/live: this cycle's activity, then the live events
    floor = livefeed.floor  # the newest activity seq of an earlier cycle: the phone feed drops it (T2479)

    def _act(self, call: Callable[[], object]) -> None:
        try:
            call()
        except RunnerError as exc:  # its ctor is (message, code): the reverse of BackendError
            code = exc.code if exc.code in ERROR_CODES else "internal"
            raise BackendError(code, exc.message) from exc
        except LessonError as exc:
            raise BackendError(CONFLICT, str(exc)) from exc
        except TodoError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
        self.cache.poke()

    def _click(self, id8: str, kind: str, call: Callable[[], object]) -> None:
        """Run an action of kuhy's and, once it is accepted, record it as an intervention (never Ship)."""
        self._act(call)
        record(self.root, id8, kind, self._clock())

    def start(self, id8: str, *, auto_ship: bool | None = None) -> None:
        """Start click (a retry on a card that has a run); `auto_ship` None keeps the stored choice."""
        kind = "start" if load(run_dir(self.root, id8)) is None else "retry"
        starter = self.triage_service or self.scheduler  # a new-repo card is created first (DOCS-triage.md)
        self._click(id8, kind, lambda: starter.start(id8, auto_ship=auto_ship))

    def spec_answers(self, id8: str, answers: dict[str, str]) -> None:
        """Answers to spec questions."""
        self._click(id8, "spec_answers", lambda: self.scheduler.spec_answers(id8, answers))

    def spec_ok(self, id8: str) -> None:
        """Spec OK click."""
        self._click(id8, "spec_ok", lambda: self.scheduler.spec_ok(id8))

    send = notes.send  # Send to Claude; a model note pins it (modelpick), a gate note drafts a lesson
    model = notes.model  # the model picker

    def _draft(self, id8: str, note: str) -> None:
        directory = run_dir(self.root, id8)
        try:
            draft_lesson(directory, note, run_skills(directory), self.drafter)
        except Exception:
            log.exception("lesson draft for %s failed", id8)

    def ship(self, id8: str) -> None:
        """Ship click."""
        self._act(lambda: self.scheduler.ship(id8))

    def close(self, id8: str) -> None:
        """Close click: re-run the done_check, then close the item (closing runs only)."""
        self._act(lambda: self.scheduler.close_item(id8))

    def cancel(self, id8: str) -> None:
        """Cancel click."""
        self._click(id8, "cancel", lambda: self.scheduler.cancel(id8))

    def go(self, id8: str) -> None:
        """Go click: run the card's one-line command as kuhy, rerun the blocked stage on exit 0."""
        run = permission.go
        self._click(id8, "go", lambda: run(self.root, self.scheduler, id8, self.fix_runner, self._clock()))

    def rerun(self, id8: str) -> None:
        """Done, rerun click."""
        self._click(id8, "rerun", lambda: permission.rerun(self.root, self.scheduler, id8))

    def lesson_approve(self, id8: str, lesson_id: str) -> None:
        """Write the drafted lesson into its skill."""
        self._act(lambda: approve(run_dir(self.root, id8), lesson_id))
