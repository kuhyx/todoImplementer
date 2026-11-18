"""Create kuhy's task: images in a fresh dufs folder, a `## title` section linking them, its card at once."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from todoimpl.http.backend import BackendError
from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.model import TodoError, upstream_text

from . import images, uploads

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.http.newtask import NewTask
    from todoimpl.service.cache import TaskCache
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient

UPSTREAM, NOT_FOUND, CONFLICT, BAD = "upstream_unavailable", "not_found", "conflict", "bad_request"


def _fresh_folder() -> str:
    return str(uuid.uuid4())  # the todo renderer only needs [A-Za-z0-9_-]+, never the note id


def _holds(card: CardTask, note8: str, title: str) -> bool:
    """Tell whether this open card carries the section `title` of note `note8` (as a part or the section)."""
    if card.status == "done":
        return False
    found = [(part.note_id[:8], part.title) for part in card.parts] or [(card.item.note_id[:8], card.title)]
    return (note8, title) in found


class NewTaskService:
    """Implements todoimpl.http.newtask.NewTaskApi over the todo client and the board cache."""

    def __init__(
        self, client: TodoClient, cache: TaskCache, folder: Callable[[], str] = _fresh_folder
    ) -> None:
        """Wire the pieces; `folder` names a new image folder (tests pin it)."""
        self._client = client
        self._cache = cache
        self._folder = folder

    def create(self, task: NewTask) -> tuple[str, str]:
        """Add the section and return (note id8, the card that holds it now)."""
        try:
            self._refuse_twin(task)
            staged = uploads.claim(task.files, uploads.root())
            if isinstance(staged, str):
                raise BackendError(BAD, staged)
            folder = self._folder() if task.images or staged else ""
            links = [f"![]({link})" for link in images.save(task.images, images.root(), folder)]
            links += images.attach(staged, images.root(), folder)
            body = "\n\n".join([task.body, *links]).strip()
            note = self._client.add_task(task.repo, task.title, body)
        except TodoError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
        self._cache.refresh()  # Start looks the card up in the cache: a poke would answer before it is there
        note8 = note.id[:8]
        card = next((c.id for c in self._cache.snapshot().tasks if _holds(c, note8, task.title)), None)
        if card is None:
            msg = f"note {note8} got the task, but its card is not on the board yet"
            raise BackendError(NOT_FOUND, msg)
        return note8, card

    def check_twin(self, task: NewTask) -> None:
        """Refuse (BackendError) a title the repo has open already; a session handoff checks a batch first."""
        try:
            self._refuse_twin(task)
        except TodoError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc

    def _refuse_twin(self, task: NewTask) -> None:
        """Refuse a title an open section has already: two parts nobody could tell apart."""
        for note in self._client.list_tasks(repo=task.repo, full=True):
            if any(c.title == task.title and c.status != "done" for c in card_tasks(note)):
                msg = f"{task.repo} already has an open part titled {task.title!r}"
                raise BackendError(CONFLICT, msg)
