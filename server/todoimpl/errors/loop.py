"""The errors loop: one ticket per open error, and its card is started when the gate says so.

Per tick: (1) tell sources about shipped fixes (`settle`), (2) for each open record make, find or update its
ticket, (3) start at most ONE card whose tickets are not started yet (`gate.Gate`). Cards that were skipped
because usage was high are looked at again on every tick, so they start after the weekly reset.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.board.status import CYCLE_ENDS
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.stall.report import is_stall
from todoimpl.todo_mcp.model import TodoError

from . import ledger, settle, ticket
from . import sources as sources_mod
from .gate import Gate
from .marks import KEY
from .ports import Creator, Starter, Tasks

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    from todoimpl.service.cards import CardTask

    from .record import AppError

log = logging.getLogger("todoimpl.errors")
INTERVAL = 60.0
MAX_STARTS = 3  # starts per ticket: a part the session never ticks must not loop forever
MISSING_TICKS = 2  # ticks a ticket may be gone before it counts as closed by hand (a Ship may be closing it)


def _epoch(text: str) -> float | None:
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def _reopens(entry: dict[str, Any], record: AppError) -> int | None:
    """Return the fixed build when this report is a regression, else None (old build, or before the install).

    With a build number on both sides the build decides. Without one, only an event that happened after the
    fix was installed counts: the phone may still send what it logged before.
    """
    fixed = int(entry.get("fixed_build", 0))
    if record.build > 0 and fixed > 0:
        return fixed if record.build >= fixed else None
    installed, seen = entry.get("installed_at"), _epoch(record.last_seen)
    return fixed if isinstance(installed, int | float) and seen is not None and seen > installed else None


class ErrorLoop:
    """One thread, a tick every `interval` seconds (the first at once); `tick()` is the testable step."""

    def __init__(  # noqa: PLR0913 - collaborators, all injectable for tests
        self,
        root: Path,
        *,
        cards: Callable[[], Sequence[CardTask]],
        tasks: Tasks,
        creator: Creator,
        starter: Starter,
        gate: Gate | None = None,
        sources: Callable[[], Sequence[sources_mod.Source]] = sources_mod.configured,
        refresh: Callable[[], object] = lambda: None,
        clock: Callable[[], float] = time.time,
        interval: float = INTERVAL,
    ) -> None:
        """Nothing runs until tick() or start()."""
        self.root, self.cards, self.tasks, self.creator, self.starter = root, cards, tasks, creator, starter
        self.gate, self.sources, self.refresh = gate or Gate(), sources, refresh
        self.clock, self.interval = clock, interval
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="app-errors", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread after its current tick."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("app-errors tick failed")
            self._stop.wait(self.interval)

    def tick(self) -> None:
        """Settle shipped fixes, keep one ticket per open error, then start at most one card."""
        found = sources_mod.records(self.sources())
        owners = {record.app: source for source, record in found}
        settle.settle(self.root, owners | {s.app: s for s in self.sources()})
        cards = list(self.cards())
        for _source, record in found:
            if record.open:
                self._track(record, cards)
        self._start_one(list(self.cards()))

    def _track(self, record: AppError, cards: Sequence[CardTask]) -> None:
        entry = ledger.load(self.root).get(record.key)
        state = entry.get("state") if entry else None
        if state == "shipped":
            return  # the source is told first (settle), on the next tick
        if entry is not None and state == "fixed":
            if (fixed := _reopens(entry, record)) is None:
                return
            ledger.drop(self.root, record.key)
            self._create(record, fixed)
            return
        found = ticket.find(cards, record.key)
        if entry is None:
            if found is None:
                self._create(record, None)
            else:  # the ledger was lost: take the ticket the board already has
                self._adopt(record, found)
        elif found is None:
            self._missing(record, entry)
        else:
            if entry.get("missing"):
                ledger.put(self.root, record.key, missing=0)
            if entry.get("count") != record.count:
                self._seen(record, found)

    def _put(self, record: AppError, title: str, **fields: object) -> None:
        ledger.put(self.root, record.key, state="ticket", repo=record.repo, title=title, **fields)

    def _create(self, record: AppError, regression: int | None) -> None:
        title = ticket.title(record)
        try:
            self.creator.create(NewTask(record.repo, title, ticket.body(record, regression=regression), ()))
        except BackendError as exc:  # a twin title, or the todo app is down: the next tick tries again
            log.warning("error %s: no ticket made: %s", record.key, exc.message)
            return
        self._put(record, title, count=record.count, starts=0, missing=0)

    def _adopt(self, record: AppError, found: ticket.Found) -> None:
        self._put(record, found.title, count=0, starts=0, missing=0)
        self._seen(record, found)

    def _missing(self, record: AppError, entry: dict[str, Any]) -> None:
        """Handle a part not on the board: closed by hand (make a new one) or closing now (wait a tick)."""
        gone = int(entry.get("missing", 0)) + 1
        if gone < MISSING_TICKS:
            ledger.put(self.root, record.key, missing=gone)
            return
        ledger.drop(self.root, record.key)
        self._create(record, None)

    def _seen(self, record: AppError, found: ticket.Found) -> None:
        """Rewrite the part's `Seen:` line (only when it differs) and remember the count."""
        try:
            note = self.tasks.get_task(found.note)
            if (text := ticket.refresh(note.body, record.key, ticket.seen(record))) is not None:
                self.tasks.update_task(found.note, body=text)
        except TodoError as exc:
            log.warning("error %s: count not updated: %s", record.key, exc)
            return
        ledger.put(self.root, record.key, count=record.count)

    def _cheap(self, parts: Sequence[tuple[str, ticket.Found]]) -> None:
        """Free models take the card only when its part says `Tier: cheap`: add that line before the start."""
        for key, found in parts:
            try:
                note = self.tasks.get_task(found.note)
                if (text := ticket.add_tier(note.body, key)) is not None:
                    self.tasks.update_task(found.note, body=text)
            except TodoError as exc:
                log.warning("error %s: tier line not added: %s", key, exc)
        self.refresh()

    def _wanted(self, cards: Sequence[CardTask]) -> dict[str, list[tuple[str, ticket.Found]]]:
        """Return card id -> its tickets that may still start (open part, fewer than MAX_STARTS), by key."""
        wanted: dict[str, list[tuple[str, ticket.Found]]] = {}
        for key, entry in ledger.load(self.root).items():
            if entry.get("state") != "ticket" or int(entry.get("starts", 0)) >= MAX_STARTS:
                continue
            if (found := ticket.find(cards, key)) is not None:
                wanted.setdefault(found.card, []).append((key, found))
        return wanted

    def _resting(self, card: str) -> bool:
        """Say whether the card has no run, or one whose cycle shipped with parts left."""
        try:
            run = store.load(self.root / card)
        except StateError:
            return False
        return run is None or run.stage in CYCLE_ENDS

    def _start_one(self, cards: Sequence[CardTask]) -> None:
        from todoimpl.runner.scheduler import RunnerError  # noqa: PLC0415 - the scheduler imports the service

        now = self.clock()
        data = ledger.load(self.root)
        # A stall ticket (DOCS-errors.md, "Stalls") goes first and skips the usage gate: kuhy's top priority.
        wanted = sorted(self._wanted(cards).items(), key=lambda kv: not any(is_stall(k) for k, _f in kv[1]))
        for card, parts in wanted:
            keys = [key for key, _found in parts]
            if not self._resting(card):
                continue
            stall = any(is_stall(key) for key in keys)
            reason = "stall" if stall else self.gate.check(self.root, str(data[keys[0]]["repo"]), now)
            if reason is None:
                continue
            if reason == "free":
                self._cheap(parts)
            try:
                self.starter.start(
                    card, auto_ship=True, extra={KEY: {"reason": reason, "keys": keys, "at": now}}
                )
            except RunnerError as exc:
                log.warning("app error card %s not started: %s", card, exc.message)
                continue
            for key in keys:
                ledger.put(self.root, key, starts=int(data[key].get("starts", 0)) + 1)
            return
