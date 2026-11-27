"""The TodoClient as the runner sees it: ids are card ids, one section per task, closing marks one section."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from todoimpl.repotask import files, legacy
from todoimpl.repotask.legacy import Older
from todoimpl.runner.parsing import for_part
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import Task, TodoError
from todoimpl.umbrella.note import is_umbrella

from .cards import CardTask, card_tasks
from .repocards import group_cards, released_in

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.todo_mcp.client import TodoClient

    from .cache import TaskCache

PASS_THROUGH = frozenset({"status", "priority", "repo"})
log = logging.getLogger("todoimpl.service")


class ItemView:
    """Duck-types TodoClient for the Scheduler. Reads are fresh (get_task) or cached (list_tasks)."""

    def __init__(self, client: TodoClient, cache: TaskCache, root: Path | None = None) -> None:
        """Wrap client; cache resolves card ids to notes and is poked after writes; `root` = the run root."""
        self._client = client
        self._cache = cache
        self._root = root
        self._tick = (
            threading.Lock()
        )  # children finish concurrently: one read-modify-write of the note at a time

    def _note_of(self, card: str) -> str:
        snap = self._cache.snapshot()
        for task in snap.tasks:
            if task.id == card and task.parts:
                msg = f"{card} is a repo task: it spans several notes"
                raise TodoError(msg)
            if task.id == card:
                return task.item.note_id
        # Before the first good load (boot, MCP still down) a miss proves nothing: report it as transient.
        msg = f"unknown task {card}" if snap.loaded else f"todo app offline, {snap.error}"
        raise TodoError(msg)

    def _repo_card(self, card: str) -> CardTask | None:
        """Return the cached repo task of this card id, None when it is a section card."""
        return next((t for t in self._cache.snapshot().tasks if t.id == card and t.parts), None)

    def _fresh_repo(self, found: CardTask) -> CardTask:
        """Rebuild a repo task from its notes, read now: the parts it has left."""
        notes = self._client.list_tasks(repo=found.repo, full=True)
        root = self._root
        cards = group_cards(
            notes, lambda key: legacy.older(root, key) if root is not None else Older(), released_in(root)
        )
        for task in cards:
            if task.id == found.id:
                return task
        msg = f"repo task {found.id} has no open part left"
        raise TodoError(msg)

    def get_task(self, card: str) -> CardTask:
        """Fetch the note fresh and return the section behind this card id (a repo task: its fresh parts)."""
        if (repo_card := self._repo_card(card)) is not None:
            return self._fresh_repo(repo_card)
        for task in card_tasks(self._client.get_task(self._note_of(card))):
            if task.id == card:
                return task
        msg = f"section of {card} moved or gone"
        raise TodoError(msg)

    def list_tasks(self, status: str | None = None, repo: str | None = None) -> list[CardTask]:
        """Return the cached cards, filtered; raise the refresh error instead of returning nothing."""
        snap = self._cache.snapshot()
        if snap.error:
            raise TodoError(snap.error)
        return [t for t in snap.tasks if status in (None, t.status) and repo in (None, t.repo)]

    def set_note_priority(self, note: str, priority: str) -> None:
        """Set one note's priority (a card's priority pick, T2583); the caller refreshes the cache."""
        self._client.update_task(note, priority=priority)

    def update_task(self, card: str, **fields: str | None) -> CardTask:
        """Change note-level fields (status, priority, repo); title/body edits are refused."""
        if set(fields) - PASS_THROUGH:
            msg = f"only {sorted(PASS_THROUGH)} can change through a card"
            raise TodoError(msg)
        self._client.update_task(self._note_of(card), **fields)
        self._cache.poke()
        return self.get_task(card)

    def close_task(self, card: str, evidence: str) -> None:
        """Mark this section done (a repo task: its ticked parts); the note closes with its last section."""
        task = self.get_task(card)
        if task.parts:
            self._close_parts(task, evidence)
        else:
            self._client.close_item(task.item, evidence)
        self._cache.poke()

    def _close_parts(self, task: CardTask, evidence: str) -> None:
        """Close the section of every part the run ticked; the other parts stay open for the next cycle."""
        if self._root is None or not (done := files.ticked(self._root / task.id, task.item)):
            msg = f"{task.id}: no part is ticked, nothing to close"
            raise TodoError(msg)
        for part in done:  # close_item re-reads the note and fails closed on a section that moved
            item = Item(part.note_id, part.index, part.title, part.body, task.repo, "todo", part.done_check)
            self._client.close_item(item, for_part(evidence, part.key))  # its own live rows only (T2460)

    def tick_child(self, card: str, cid: str, mark: str = "x") -> None:
        """Tick child `cid`'s checkbox in the umbrella note behind `card` (`mark` `-` drops it)."""
        with self._tick:
            self._client.tick_child(self._note_of(card), cid, mark)
        self._cache.poke()

    def abandon(self, card: str) -> bool:
        """Set the note abandoned when this card is its only open section; True when it did (T1815)."""
        if self._repo_card(card) is not None:  # the notes of a repo task hold other parts too
            return False
        note = self._note_of(card)
        task = self._client.get_task(note)
        if is_umbrella(task.body):  # an umbrella note outlives a Cancel: its children stay open (T1921)
            return False
        cards = card_tasks(task)
        if any(t.id != card and t.status != "done" for t in cards):
            return False
        self._client.update_task(note, status="abandoned")
        self._cache.poke()
        return True

    def wont(self, card: str) -> None:
        """Abandon every note behind the card (T2045); refuse before any write when one holds other work."""
        found = next((t for t in self._cache.snapshot().tasks if t.id == card), None)
        if found is None:
            msg = f"unknown task {card}"
            raise TodoError(msg)
        parts = [p for p in found.item.parts if not p.held]  # a held part still runs on its own card
        keys = {p.key for p in parts} or {card}
        ids = list(dict.fromkeys(p.note_id for p in parts)) or [found.item.note_id]
        notes = [self._client.get_task(n) for n in ids]
        for note in notes:
            if others := [t.id for t in card_tasks(note) if t.status != "done" and t.id not in keys]:
                msg = f"note {note.id[:8]} has open work on other cards: {', '.join(others)}"
                raise TodoError(msg)
        for note in notes:
            self._client.update_task(note.id, status="abandoned")
        self._cache.poke()

    def done_manually(self, card: str, evidence: str) -> CardTask:
        """Close every note behind the card as done (T2064): its parts but a held one, or its section."""
        found = next((t for t in self._cache.snapshot().tasks if t.id == card), None)
        if found is None:
            msg = f"unknown task {card}"
            raise TodoError(msg)
        parts = [p for p in found.item.parts if not p.held]  # a held part still runs on its own card
        items = [Item(p.note_id, p.index, p.title, p.body, found.repo, "todo", p.done_check) for p in parts]
        for item in items or [found.item]:
            self._client.close_item(item, evidence)
        return found

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        """Add a section to the repo's open note (a follow-up) and refresh the cached cards.

        Idempotent by title: a retry after a lost reply finds the section it already added. The repo's cards
        are read again before the return, so a drive that starts next finds the new part (T2528).
        """
        for note in self._client.list_tasks(repo=repo, full=True):
            if any(card.title == title and card.status != "done" for card in card_tasks(note)):
                return note
        task = self._client.add_task(repo, title, body)
        self._cache.poke()
        try:
            self._cache.refresh_repo(repo)
        except TodoError:  # the poked refresh brings it in a moment
            log.warning("repo %s not read again after a new part", repo)
        return task
