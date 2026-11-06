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
        for task in self._cache.snapshot().tasks:
            if task.id == card:
                return task.item.note_id
        msg = f"unknown task {card}"
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

    def add_task(self, repo: str, title: str, body: str = "") -> Task:
        """Add a section to the repo's open note (a follow-up) and refresh the cached cards."""
        task = self._client.add_task(repo, title, body)
        self._cache.poke()
        return task
