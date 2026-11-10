"""Run engine: a FIFO of card ids, a thread per drive (no cap on parallel runs), limit pause, recovery."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from functools import partial
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.credits import marks, route
from todoimpl.todo_mcp.model import TodoError
from todoimpl.umbrella.driver import driver_for
from todoimpl.usage.limits import UNTIL_FILE

from . import adopt, limits, live, orphans, retry
from .bus import Bus
from .files import read_json, write_json
from .pipeline import WORK_STAGES, Ctx

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.model import Task

    from .launch import Handle

log = logging.getLogger("todoimpl.runner")
INBOX = "inbox.json"
IDLE_WAIT = 5.0


class Client(Protocol):
    """The service's ItemView as the runner uses it (card ids `<note id8>-<n>`)."""

    def get_task(self, card: str) -> CardTask: ...  # noqa: D102
    def close_task(self, card: str, evidence: str) -> None: ...  # noqa: D102
    def add_task(self, repo: str, title: str, body: str = "") -> Task: ...  # noqa: D102
    def abandon(self, card: str) -> bool: ...  # noqa: D102


class Engine:
    """Queue and workers; `Scheduler` adds the click actions on top."""

    def __init__(self, client: Client, root: Path, check_timeout: float, clock: Callable[[], float]) -> None:
        """Recover interrupted runs, then start the dispatcher that gives every queued card its own thread."""
        self.client, self.root, self.clock, self.check_timeout = client, root, clock, check_timeout
        self.bus = Bus(root)
        self._cv = threading.Condition()
        self._queue: deque[str] = deque()
        self._active: set[str] = set()
        self._procs: dict[str, Handle] = {}
        self._cancel: set[str] = set()
        self._closed = False
        self.recover()
        self._drives: set[threading.Thread] = set()
        self._dispatcher = threading.Thread(target=self._dispatch, name="runner-dispatch", daemon=True)
        self._dispatcher.start()

    def recover(self) -> None:
        """Re-queue runs a restart interrupted; a half-done ship is never redone on its own."""
        for path in sorted(self.root.glob("*/state.json")):
            try:
                st = store.load(path.parent)
            except StateError:
                continue
            if st is None:  # pragma: no cover - the file was just globbed
                continue
            if st.stage == "shipping":
                st.extra["failed_stage"] = "gate"
                st.error = (
                    "Ship was interrupted by a restart: check origin and the note before shipping again"
                )
                st.stage = "failed"
                store.save(path.parent, st)
            elif live.rejudgeable(st):  # judged under older rules: judge the stored report again, no turn
                st.stage, st.error, st.last_tag, st.assignee = "live_check", None, None, "claude"
                st.extra.pop("failed_stage", None)
                st.extra["resettle"] = True
                store.save(path.parent, st)
                self._queue.append(st.task_id)
            elif st.stage in (*WORK_STAGES, "paused_limit", retry.PAUSED) and (
                st.last_tag not in ("Q", "A") or orphans.read(path.parent) is not None
            ):  # a turn still recorded means last_tag is stale: it is running or its result waits
                self._queue.append(st.task_id)

    def close(self) -> None:
        """Stop the dispatcher and the drives (after their current turn) and end every subscription."""
        with self._cv:
            self._closed = True
            self._cv.notify_all()
        self.bus.close()
        self._dispatcher.join(timeout=10)
        with self._cv:
            drives = list(self._drives)
            for handle in self._procs.values():
                handle.detach.set()  # the drive lets go of its turn; the turn itself keeps running
        for drive in drives:
            drive.join(timeout=10)

    def running(self) -> set[str]:  # noqa: D102
        with self._cv:
            return set(self._active)

    def enqueue(self, card: str, *, first: bool = False) -> None:
        """Queue a drive; callers hold the lock."""
        if card not in self._queue:
            (self._queue.appendleft if first else self._queue.append)(card)
        self._cv.notify_all()

    def save(self, card: str, st: RunState) -> None:
        """Persist and announce a stage change made outside a drive; callers hold the lock."""
        st.updated = self.clock()
        store.save(self.root / card, st)
        self.bus.publish(card, {"type": "stage", "stage": st.stage})

    def push_note(self, card: str, text: str) -> None:
        """Queue a Send-to-Claude note for the run's next turn; callers hold the lock."""
        path = self.root / card / INBOX
        write_json(path, [*(read_json(path) or []), text])

    def _drain(self, card: str) -> list[str]:
        with self._cv:
            path = self.root / card / INBOX
            notes = [str(n) for n in read_json(path) or []]
            path.unlink(missing_ok=True)
            return notes

    def _register(self, card: str, handle: Handle | None) -> None:
        with self._cv:
            if handle is None:
                self._procs.pop(card, None)
                return
            self._procs[card] = handle
            if card not in self._cancel:
                return
        threading.Thread(target=handle.stop, daemon=True).start()

    def kill(self, card: str) -> None:
        """Cancel a live drive: flag it and stop its turn (an adopted one too); callers hold the lock."""
        self._cancel.add(card)
        handle = self._procs.get(card)
        if handle is not None:
            threading.Thread(target=handle.stop, daemon=True).start()

    def _retry_wait(self, card: str, now: float) -> float:
        """Seconds a run in paused_retry still waits (its own timer, not the global limit file)."""
        st = store.load_runs(self.root, [card]).get(card)
        if st is None or st.stage != retry.PAUSED or st.resume_at is None:
            return 0.0
        return st.resume_at - now

    def _take(self) -> str | None:
        with self._cv:
            while not self._closed:
                now = self.clock()
                until = limits.active_until(self.root, now)
                if until is None and (self.root / UNTIL_FILE).exists():
                    limits.clear(self.root)
                if until is None:
                    marks.clear_exhausted(self.root)
                free = until is None or route.choose(self.root, now).route == route.CREDITS
                wake = IDLE_WAIT if until is None else min(until - now, IDLE_WAIT)
                for card in [c for c in self._queue if c not in self._active]:
                    if (hold := self._retry_wait(card, now)) > 0:
                        wake = min(wake, hold)
                    elif free:
                        self._queue.remove(card)
                        self._active.add(card)
                        return card
                self._cv.wait(wake)
            return None

    def _dispatch(self) -> None:
        """Start a thread per taken card: a start never waits behind other runs."""
        while (card := self._take()) is not None:
            drive = threading.Thread(target=self._work, args=(card,), name=f"runner-{card}", daemon=True)
            with self._cv:
                self._drives.add(drive)
            drive.start()

    def _work(self, card: str) -> None:
        try:
            self._drive(card)
        except adopt.Detached:
            log.info("drive of %s let go of its turn: the server is closing", card)
        except Exception:
            log.exception("drive of %s crashed", card)
        finally:
            with self._cv:
                self._active.discard(card)
                self._procs.pop(card, None)
                self._cancel.discard(card)
                self._drives.discard(threading.current_thread())
                self.after_drive(card)
                self._cv.notify_all()
            self.bus.publish(card, {"type": "done"})

    def after_drive(self, card: str) -> None:
        """Let the Scheduler react (paused runs and pending notes); callers hold the lock."""

    def _drive(self, card: str) -> None:
        run_dir = self.root / card
        st = store.load(run_dir)
        if st is None:
            return
        if adopt.reap_legacy(run_dir):  # a pipe-spawned turn of the previous version has no reader
            lost = "turn lost: a turn started by the previous server version has no exit record"
            self.bus.publish(
                card, {"type": "activity", "at": self.clock(), "kind": "error", "text": lost, "tool": None}
            )
        try:
            item = self.client.get_task(card).item
        except TodoError as exc:
            if retry.is_transient(str(exc)):
                wait = retry.later(st, self.clock(), f"todo app unreachable: {exc}", "todo")
                retry.pause(st, wait.until, wait.why, wait.kind)
            else:
                st.extra["failed_stage"] = st.stage
                st.error = f"The todo app could not be read: {exc}"
                st.stage = "failed"
            with self._cv:
                self.save(card, st)
            return
        publish: Callable[[dict[str, Any]], None] = partial(self.bus.publish, card)
        ctx = Ctx(
            self.root, run_dir, self.client, publish, partial(self._register, card), self.clock,
            lambda: card in self._cancel, self.check_timeout, partial(self._drain, card),
        )  # fmt: skip
        driver_for(ctx, st, item).run()


def default_clock() -> float:  # noqa: D103
    return time.time()
