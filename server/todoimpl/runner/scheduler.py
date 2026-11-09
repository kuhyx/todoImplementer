"""Scheduler the service drives: start, spec answers, Spec OK, send, ship, cancel, events."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.state import RunState, clip_body
from todoimpl.board.types import MANUAL_REASON, is_manual
from todoimpl.todo_mcp.model import TodoError

from . import adopt, retry
from .engine import Client, default_clock
from .files import read_json
from .phone_sched import PhoneEngine

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from todoimpl.todo_mcp.items import Item

log = logging.getLogger("todoimpl.runner")
SPEC_MARKER = re.compile(r"^\s*(done|verify|done_check)\s*:", re.IGNORECASE | re.MULTILINE)
RESTARTABLE = ("failed", "cancelled")
FINAL = ("shipped", "cancelled")
RESUMABLE = ("spec", "plan", "implement", "live_check", "checks")
COUNTERS = (
    "failure_tail", "live_fixes", "check_fixes", "nudges", "nudge", "failed_stage", "resume_stage",
    "resettle", "retries", "crash_retries", "r_continues", "r_continue", "tagless_retry", "fresh",
    "ship_fixes", "reship", "hands_nudged",
)  # fmt: skip


class RunnerError(Exception):
    """A refused action; `code` is a contracts error code (not_found, conflict, disabled, bad_request)."""

    def __init__(self, message: str, code: str) -> None:  # noqa: D107
        super().__init__(message)
        self.code = code
        self.message = message


def needs_spec(item: Item) -> bool:
    """Spec runs only when the note says neither a done_check nor done/verify lines."""
    return item.done_check is None and not SPEC_MARKER.search(item.body)


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

    def _idle(self, card: str) -> RunState:
        if card in self._active:
            msg = f"{card} has a turn running: wait for it to end"
            raise RunnerError(msg, "conflict")
        return self._load(card)

    def start(self, card: str, *, auto_ship: bool | None = None) -> None:
        """Start, Restart, Retry or Hand back; a failed run (Retry, Hand back) keeps its auto-ship choice."""
        try:
            item = self.client.get_task(card).item
        except TodoError as exc:
            msg = str(exc)
            raise RunnerError(msg, "not_found") from exc
        if is_manual(item.title):
            raise RunnerError(MANUAL_REASON, "disabled")
        with self._cv:
            if card in self._active or card in self._queue:
                msg = f"{card} is already running"
                raise RunnerError(msg, "conflict")
            st = store.load(self.root / card)
            if st is not None and st.stage not in RESTARTABLE:
                msg = f"{card} already has a run ({st.stage})"
                raise RunnerError(msg, "conflict")
            if st is None or st.stage == "cancelled":
                st = st or RunState(task_id=card, stage="spec", started_at=self.clock(), repo=item.repo)
                st.auto_ship = bool(auto_ship)
            failed = st.extra.get("failed_stage") if st.stage == "failed" else None
            st.stage = "plan" if st.extra.get("spec_ok") or not needs_spec(item) else "spec"
            if failed in RESUMABLE:
                st.stage = str(failed)
            st.error, st.last_tag, st.assignee = None, None, "claude"
            st.note_body = clip_body(item.body)
            for key in COUNTERS:
                st.extra.pop(key, None)
            if failed in ("shipping", "gate"):
                st.stage = "gate"
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

    def send(self, card: str, text: str) -> None:  # noqa: D102
        if not text.strip():
            msg = "The message is empty"
            raise RunnerError(msg, "bad_request")
        with self._cv:
            st = self._load(card)
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
            if st.stage != "gate":
                msg = "Ship is offered only at Ready to ship"
                raise RunnerError(msg, "disabled")
            st.stage = "shipping"
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
