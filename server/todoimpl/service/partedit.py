"""Write a part's new title and text into its note section (856c0f0a), then show it on the card at once.

The route has already checked the card offers the edit (board/partedit.py). This is the one narrow path for
a part's own text: `ItemView.update_task` keeps refusing title and body edits through a card.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.http.backend import BackendError
from todoimpl.todo_mcp.edit import EditError
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import TodoError, UnreachableError, upstream_text

if TYPE_CHECKING:
    from todoimpl.repotask.model import Part
    from todoimpl.todo_mcp.client import TodoClient

    from .cache import TaskCache
    from .cards import CardTask

BAD, UPSTREAM, CONFLICT, MISSING = "bad_request", "upstream_unavailable", "conflict", "not_found"


class PartEditService:
    """Edits one open part of a repo card through the todo MCP client."""

    def __init__(self, client: TodoClient, cache: TaskCache) -> None:
        """Keep the client that writes and the cache that shows the result."""
        self._client = client
        self._cache = cache

    def _find(self, card: str, key: str) -> tuple[CardTask, Part]:
        task = next((t for t in self._cache.snapshot().tasks if t.id == card), None)
        part = next((p for p in task.parts if p.key == key), None) if task is not None else None
        if task is None or part is None:
            msg = f"card {card} has no part {key}"
            raise BackendError(MISSING, msg)
        return task, part

    def edit(self, card: str, part: str, title: str, body: str) -> None:
        """Rewrite the part's section (or its section-less note); refusals are BackendError."""
        task, found = self._find(card, part)
        item = Item(found.note_id, found.index, found.title, found.body, task.repo, "todo", found.done_check)
        try:
            self._client.edit_section(item, title, body)
        except EditError as exc:
            raise BackendError(BAD, str(exc)) from exc
        except UnreachableError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
        except TodoError as exc:  # the section moved or closed since the board read it
            raise BackendError(CONFLICT, str(exc)) from exc
        try:
            self._cache.refresh_repo(task.repo or "")  # the card shows the new text in this reply
        except TodoError:
            self._cache.poke()  # the write landed; the next refresh shows it
