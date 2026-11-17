"""Scheduler the service drives: start, spec answers, Spec OK, send, ship, cancel, events."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.parts import kuhys
from todoimpl.board.state import RunState, clip_body
from todoimpl.board.types import MANUAL_REASON
from todoimpl.repotask.start import prepare
from todoimpl.todo_mcp.model import TodoError

from . import adopt, appfix, closing, retry
from .engine import Client, default_clock
from .files import read_json
from .phone_sched import PhoneEngine
from .restart import restart_stage

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path


log = logging.getLogger("todoimpl.runner")
RESTARTABLE = ("failed", "cancelled")
FINAL = ("shipped", "closed", "cancelled")
COUNTERS = (
    "failure_tail", "live_fixes", "check_fixes", "nudges", "nudge", "failed_stage", "resume_stage",
    "resettle", "retries", "crash_retries", "r_continues", "r_continue", "tagless_retry", "fresh",
    "ship_fixes", "reship", "hands_nudged", "ask_grants", "ask_grant_total", "part_nudges", "ship_resumes",
    "phone_update",
)  # fmt: skip


class RunnerError(Exception):
    """A refused action; `code` is a contracts error code (not_found, conflict, disabled, bad_request)."""

    def __init__(self, message: str, code: str) -> None:  # noqa: D107
        super().__init__(message)
        self.code = code
        self.message = message


class Scheduler(PhoneEngine):
    """Every start drives at once in its own thread; only the usage limit holds a run back."""

    def __init__(
        self,
        client: Client,
        root: Path | None = None,
        *,
        check_timeout: float = 600.0,
        clock: Callable[[], float] = default_clock,
    ) -> None:
        """Root defaults to `$TODOIMPL_HOME` or ~/.cache/todoImplementer."""
        super().__init__(client, root or store.run_root(), check_timeout, clock)

    def _load(self, card: str) -> RunState:
        st = store.load(self.root / card)
        if st is None:
            msg = f"{card} has no run yet: start it first"
            raise RunnerError(msg, "not_found")
        return st

    def idle(self, card: str) -> RunState:
        """Return the run of a card with no live drive; callers hold the lock."""
        if card in self._active:
            msg = f"{card} has a turn running: wait for it to end"
            raise RunnerError(msg, "conflict")
        return self._load(card)

    _idle = idle

    def busy(self, card: str) -> bool:
        """Return True while the card is queued or driving; callers hold the lock."""
        return card in self._active or card in self._queue

    def mark_active(self, card: str, *, active: bool) -> None:
        """Hold a card live outside a drive (the Close re-run); callers hold the lock."""
        (self._active.add if active else self._active.discard)(card)

    auto_start = closing.auto_start  # a closing run when the item has none; False when one exists
    close_item = closing.close  # the Close click on a Ready-to-close run (`close` is the Engine's shutdown)
    phone_update_start = appfix.restart  # a pushed fix whose deploy waits for the phone: Ship again

    def start(self, card: str, *, auto_ship: bool | None = None, extra: dict[str, Any] | None = None) -> None:
        """Start, Restart, Retry or Hand back; a failed run (Retry, Hand back) keeps its auto-ship choice.

        `extra` goes into the run's state (the errors loop marks its cards); a new cycle forgets old marks.
        """
        try:
            item = self.client.get_task(card).item
        except TodoError as exc:
            msg = str(exc)
            raise RunnerError(msg, "not_found") from exc
        if kuhys(item.title, item.parts):
            raise RunnerError(MANUAL_REASON, "disabled")
        with self._cv:
            st = store.load(self.root / card)
            if st is not None and st.closing and st.stage not in RESTARTABLE:
                return  # the click lost the race to the auto-start: that run is the one to keep
            if self.busy(card):
                msg = f"{card} is already running"
                raise RunnerError(msg, "conflict")
            if st is not None and st.stage not in RESTARTABLE and not (item.parts and st.stage == "shipped"):
                msg = f"{card} already has a run ({st.stage})"
                raise RunnerError(msg, "conflict")
            if st is None or st.stage in ("cancelled", "shipped"):  # shipped: a repo task's next cycle
                st = st or RunState(task_id=card, stage="spec", started_at=self.clock(), repo=item.repo)
                st.auto_ship = bool(auto_ship)
                appfix.forget(st)
            if item.parts:
                prepare(st, item, self.root / card)
            st.stage = restart_stage(st, item)
            st.error, st.last_tag, st.assignee = None, None, "claude"
            st.note_body = clip_body(item.body)
            for key in COUNTERS:
                st.extra.pop(key, None)
            st.extra.update(extra or {})
            self.save(card, st)
            if st.stage != "gate":
                self.enqueue(card)

    def spec_answers(self, card: str, answers: dict[str, str]) -> None:  # noqa: D102
        with self._cv:
            st = self._idle(card)
            if st.stage != "spec_wait":
                msg = "Answers are taken only while Claude waits on spec questions"
                raise RunnerError(msg, "disabled")
            unknown = set(answers) - {q.id for q in st.spec_questions}
            if unknown:
                msg = f"No such question: {', '.join(sorted(unknown))}"
                raise RunnerError(msg, "bad_request")
            for q in st.spec_questions:
                if answers.get(q.id, "").strip():
                    q.answer = answers[q.id].strip()
            st.stage, st.last_tag = "spec", None
            self.save(card, st)
            self.enqueue(card)

    def spec_ok(self, card: str) -> None:  # noqa: D102
        with self._cv:
            st = self._idle(card)
            if st.stage != "spec_wait":
                msg = "Spec OK needs the spec stage waiting on you"
                raise RunnerError(msg, "disabled")
            if st.open_questions():
                msg = f"{len(st.open_questions())} question(s) are still open"
                raise RunnerError(msg, "disabled")
            st.extra["spec_ok"] = True
            st.stage, st.last_tag = "plan", None
            self.save(card, st)
            self.enqueue(card)

    def _route(self, st: RunState) -> None:
        """Where a note from kuhy sends a resting run: back to work in the stage that fits."""
        if st.stage == "gate":
            st.stage = "implement"
        elif st.stage == "spec_wait":
            st.stage = "spec"
        elif st.stage == "failed":
            failed = str(st.extra.pop("failed_stage", "implement"))
            st.stage = "implement" if failed in ("shipping", "gate") else failed
        elif st.stage == retry.PAUSED:
            st.resume_at = None
        st.error, st.last_tag, st.assignee = None, None, "claude"
        for key in ("live_fixes", "check_fixes", "nudges", "ship_fixes", "reship", "hands_nudged"):
            st.extra.pop(key, None)
        st.extra.pop("ask_grants", None)
        st.extra.pop("ask_grant_total", None)

    def send(self, card: str, text: str) -> None:  # noqa: D102
        if not text.strip():
            msg = "The message is empty"
            raise RunnerError(msg, "bad_request")
        with self._cv:
            st = self._load(card)
            if st.closing:
                msg = "closing runs take no notes; Start again or Cancel"
                raise RunnerError(msg, "disabled")
            if st.stage in (*FINAL, "shipping"):
                msg = f"The run is {st.stage}: nothing to send to"
                raise RunnerError(msg, "disabled")
            self.push_note(card, text.strip())
            shown = {
                "type": "activity",
                "at": self.clock(),
                "kind": "user",
                "text": text.strip(),
                "tool": None,
            }
            self.bus.publish(card, shown)
            if card not in self._active:
                self._route(st)
                self.save(card, st)
                self.enqueue(card)

    def after_drive(self, card: str) -> None:
        """Requeue a paused run at the front; reopen a resting run when a note arrived mid-turn."""
        st = store.load(self.root / card)
        if st is None:  # pragma: no cover - a drive always saves
            return
        if st.stage in ("paused_limit", retry.PAUSED):
            self.enqueue(card, first=True)
        elif read_json(self.root / card / "inbox.json") and st.stage not in (*FINAL, "shipping"):
            self._route(st)
            self.save(card, st)
            self.enqueue(card)

    def ship(self, card: str) -> None:  # noqa: D102
        with self._cv:
            st = self._idle(card)
            if st.stage != "gate" or st.closing:
                msg = "Ship is offered only at Ready to ship"
                raise RunnerError(msg, "disabled")
            st.stage = "shipping"
            st.extra.pop("ship_resumes", None)
            self.save(card, st)
            self.enqueue(card)

    def cancel(self, card: str) -> None:  # noqa: D102
        with self._cv:
            st = self._load(card)
            if st.stage in FINAL:
                msg = f"The run is already {st.stage}"
                raise RunnerError(msg, "disabled")
            if card in self._active:
                self.kill(card)
            else:
                if card in self._queue:
                    self._queue.remove(card)
                    self.locks.release(card)
                adopt.abandon(self.root / card)  # a turn no drive follows must not go on editing the worktree
                st.stage = "cancelled"
                self.save(card, st)
                self.bus.publish(card, {"type": "done"})
        try:  # a cancelled card is abandoned in the todo app too, where a whole note can be (T1815)
            self.client.abandon(card)
        except TodoError as exc:
            log.warning("cancel %s: the note stays open, the todo app refused: %s", card, exc)

    def subscribe(self, card: str, after: int = 0) -> Iterator[dict[str, Any]]:  # noqa: D102
        return self.bus.subscribe(card, after)
