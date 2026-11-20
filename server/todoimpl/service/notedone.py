"""A note marked done in the todo app puts its card in Done manually and stops its session (T2065).

The todo app lists open notes only, so a note kuhy ticks off simply leaves `list_tasks`: its card used to
vanish and a session working on it went on. After each refresh this watcher looks for the cards that left
the board and asks the todo app (`get_task`) whether their notes are done. Only `done` counts: an
abandoned or unreadable note changes nothing, a run that is shipping or closing is left to close its own
notes, and so is a note this process closed itself (`TodoClient.closed_here`: Ship, merge, the key monitor).

Two kinds of card are looked at: one of the previous snapshot that is gone, and a run dir whose card is not
on the board (a restart forgot the snapshot). A card with parts only loses a part when its note is done,
and moves to Done when none is left. It then rests like a Done manually click (`Scheduler.done_manually`):
the session stops, no turn starts, the notes are never reopened or deleted.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.board.actions import FINAL_STAGES
from todoimpl.board.parse import StateError
from todoimpl.board.state import FILE, load
from todoimpl.board.status import CYCLE_ENDS
from todoimpl.repotask import files
from todoimpl.runner.files import read_json
from todoimpl.runner.scheduler import RunnerError
from todoimpl.todo_mcp.items import split_items
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.client import TodoClient
    from todoimpl.todo_mcp.model import Task

    from .cache import TaskCache
    from .cards import CardTask
    from .scheduling import SchedulerLike

log = logging.getLogger("todoimpl.service")
INTERVAL = 2.0
QUIET = 60.0  # seconds before a card whose note is still open is asked about again
BUDGET = 10  # cards asked about per tick: the todo app answers one note at a time
RESTING = ("failed", "spec_wait")  # a run here that an open note still names was folded into a repo card
OWN_CLOSE = ("shipping",)  # the board closes the notes of a run in these stages itself


@dataclass(frozen=True)
class Gone:
    """A card that left the board: its part keys (`<note id8>-<index>`) and what a state needs to rest it."""

    card: str
    keys: tuple[str, ...]
    repo: str | None
    title: str
    repotask: bool


def _keys(card: CardTask) -> tuple[str, ...]:
    return tuple(p.key for p in card.parts if not p.held) or (card.id,)


class NoteDoneWatcher:
    """Runs on its own thread, so the scheduler's lock is never taken inside the cache's refresh."""

    def __init__(  # noqa: PLR0913 - the collaborators, all injectable
        self,
        cache: TaskCache,
        client: TodoClient,
        scheduler: SchedulerLike,
        root: Path,
        *,
        interval: float = INTERVAL,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Nothing runs until `start()`; `tick()` does one look (tests call it)."""
        self._cache, self._client, self._scheduler, self._root = cache, client, scheduler, root
        self._interval, self._clock = interval, clock
        self._seen: dict[str, CardTask] = {}  # the open cards of the last snapshot
        self._retry: dict[str, Gone] = {}  # cards the todo app could not answer for yet
        self._quiet: dict[str, float] = {}  # card -> when to ask again
        self._fails: dict[str, int] = {}  # card -> todo errors in a row for it
        self._at = 0.0
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the daemon thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="note-done", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.wait(self._interval):
            try:
                self.tick()
            except Exception:
                log.exception("note-done watcher tick failed")

    def tick(self) -> None:
        """Look at the latest snapshot once; a failed refresh or an unchanged snapshot changes nothing."""
        snap = self._cache.snapshot()
        if snap.error is not None or not snap.loaded or snap.at == self._at:
            return
        self._at = snap.at
        shown = {t.id for t in snap.tasks}
        open_cards = {t.id: t for t in snap.tasks if t.status != "done"}
        gone = {
            i: Gone(i, _keys(c), c.repo, c.title, bool(c.parts))
            for i, c in self._seen.items()
            if i not in open_cards  # gone, or turned into its Done twin
        }
        gone |= self._retry
        for found in self._runs(shown, open_cards):
            gone.setdefault(found.card, found)
        self._seen, self._retry = open_cards, {}
        notes: dict[str, Task] = {}
        for index, found in enumerate(gone.values()):
            if index < BUDGET:
                self._settle(found, notes)
            else:
                self._retry[found.card] = found

    def _runs(self, shown: set[str], open_cards: dict[str, CardTask]) -> list[Gone]:
        """Return the run dirs with a live-ish run and no card (after a restart the snapshot is empty)."""
        open_notes = {key.partition("-")[0] for card in open_cards.values() for key in _keys(card)}
        found: list[Gone] = []
        for flag in sorted(self._root.glob(f"*/{FILE}")):
            card = flag.parent.name
            if card in shown or self._quiet.get(card, 0.0) > self._clock():
                continue
            try:
                run = load(flag.parent)
            except StateError:
                continue
            if run is None or self._leaves(run):
                continue
            repotask = bool(run.extra.get("repotask"))
            keys = self._part_keys(flag.parent) if repotask else (card,)
            if run.stage in RESTING and open_notes & {key.partition("-")[0] for key in keys}:
                continue  # folded into the repo card: its note is open
            if keys:
                found.append(Gone(card, keys, run.repo, str(run.extra.get("repotask_title") or ""), repotask))
        return found

    @staticmethod
    def _leaves(run: RunState, *, repotask: bool = False) -> bool:
        """Say whether the board closes this run's notes itself, or the run is over: nothing to notice.

        A repo task whose cycle ended with parts left is not over: its new parts may be done by hand.
        """
        over = run.stage in FINAL_STAGES and not (repotask and run.stage in CYCLE_ENDS)
        return run.closing or run.stage in OWN_CLOSE or over

    @staticmethod
    def _part_keys(directory: Path) -> tuple[str, ...]:
        """Return the actionable part keys of the run's latest drive; none when it never wrote them."""
        rows = read_json(directory / files.PARTS) or []
        return tuple(str(row["key"]) for row in rows if not (row["human"] or row["held"]))

    def _settle(self, found: Gone, notes: dict[str, Task]) -> None:
        """Rest the card at Done manually when every one of its parts is done in the todo app."""
        try:
            run = load(self._root / found.card)
            done = (run is None or not self._leaves(run, repotask=found.repotask)) and all(
                self._is_done(k, notes) for k in found.keys
            )
        except TodoError as exc:  # once: ask at the next snapshot; again: wait a minute (deleted note: T2398)
            streak = self._fails[found.card] = self._fails.get(found.card, 0) + 1
            if streak == 1:
                log.warning("note-done %s: the todo app did not answer: %s", found.card, exc)
                self._retry[found.card] = found
            else:
                self._quiet[found.card] = self._clock() + QUIET
            return
        self._fails.pop(found.card, None)
        if not done:
            self._quiet[found.card] = self._clock() + QUIET
            return
        try:
            self._scheduler.done_manually(
                found.card, repo=found.repo, title=found.title, repotask=found.repotask
            )
        except RunnerError as exc:  # shipping, or already done: leave it be
            log.info("note-done %s: not rested: %s", found.card, exc.message)
            return
        log.info(
            "note-done %s: its note is done in the todo app, the card rests at done_manually", found.card
        )
        self._cache.poke()

    def _is_done(self, key: str, notes: dict[str, Task]) -> bool:
        """Say whether the part's note, or just its section, was marked done by kuhy (never by this board)."""
        note8, _, index = key.partition("-")
        if note8 in self._client.closed_here:
            return False
        note = notes.get(note8) or notes.setdefault(note8, self._client.get_task(note8))
        if note.status == "done":
            return True
        items = split_items(note) if note.status != "abandoned" else []
        return index.isdigit() and int(index) < len(items) and items[int(index)].status == "done"
