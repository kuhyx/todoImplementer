"""The TodoClient as the runner sees it: ids are card ids, one section per task, closing marks one section."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.todo_mcp.model import Task, TodoError

from .cards import CardTask, card_tasks

if TYPE_CHECKING:
    from todoimpl.todo_mcp.client import TodoClient

    from .cache import TaskCache

PASS_THROUGH = frozenset({"status", "priority", "repo"})


class ItemView:
    """Duck-types TodoClient for the Scheduler. Reads are fresh (get_task) or cached (list_tasks)."""

    def __init__(self, client: TodoClient, cache: TaskCache) -> None:
        """Wrap client; cache resolves card ids to notes and is poked after writes."""
        self._client = client
        self._cache = cache

    def _note_of(self, card: str) -> str:
        snap = self._cache.snapshot()
        for task in snap.tasks:
            if task.id == card:
                return task.item.note_id
        # Before the first good load (boot, MCP still down) a miss proves nothing: report it as transient.
        msg = f"unknown task {card}" if snap.loaded else f"todo app offline, {snap.error}"
        raise TodoError(msg)

    def get_task(self, card: str) -> CardTask:
        """Fetch the note fresh and return the section behind this card id."""
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

    def update_task(self, card: str, **fields: str | None) -> CardTask:
        """Change note-level fields (status, priority, repo); title/body edits are refused."""
        if set(fields) - PASS_THROUGH:
            msg = f"only {sorted(PASS_THROUGH)} can change through a card"
            raise TodoError(msg)
        self._client.update_task(self._note_of(card), **fields)
        self._cache.poke()
        return self.get_task(card)

    def close_task(self, card: str, evidence: str) -> None:
        """Mark this section done; the note closes once all its sections are."""
        self._client.close_item(self.get_task(card).item, evidence)
        self._cache.poke()

    def abandon(self, card: str) -> bool:
        """Set the note abandoned when this card is its only open section; True when it did (T1815)."""
        note = self._note_of(card)
        cards = card_tasks(self._client.get_task(note))
        if any(t.id != card and t.status != "done" for t in cards):
            return False
        self._client.update_task(note, status="abandoned")
        self._cache.poke()
        return True

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        """Add a section to the repo's open note (a follow-up) and refresh the cached cards.

        Idempotent by title: a retry after a lost reply finds the section it already added.
        """
        for note in self._client.list_tasks(repo=repo, full=True):
            if any(card.title == title and card.status != "done" for card in card_tasks(note)):
                return note
        task = self._client.add_task(repo, title, body)
        self._cache.poke()
        return task
