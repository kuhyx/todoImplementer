"""Create kuhy's task: images in a fresh dufs folder, a `## title` section linking them, its card at once."""

from __future__ import annotations

import time
import uuid
from dataclasses import replace
from typing import TYPE_CHECKING

from todoimpl.board.repos import canonical
from todoimpl.http.backend import BackendError
from todoimpl.merge.apply import MergeError
from todoimpl.merge.umbrella import create_umbrella
from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.model import TodoError, upstream_text

from . import images, noteimages, uploads

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.http.newtask import NewTask
    from todoimpl.service.cache import TaskCache
    from todoimpl.service.cards import CardTask
    from todoimpl.todo_mcp.client import TodoClient

UPSTREAM, NOT_FOUND, BAD = "upstream_unavailable", "not_found", "bad_request"

# The lookup forces a fetch that starts after the add (T2046); a few more tries cover a todo app that lists
# the new section a moment late.
_LOOKUPS = 4
_PAUSE_S = 0.5


def _fresh_folder() -> str:
    return str(uuid.uuid4())  # the todo renderer only needs [A-Za-z0-9_-]+, never the note id


def _pictures(task: NewTask) -> tuple[noteimages.Picture, ...]:
    """Check the task's `[Image #N]` refs before anything is written (T2321)."""
    try:
        return noteimages.resolve(task.images, uploads.root())
    except noteimages.ImageError as exc:
        raise BackendError(BAD, str(exc)) from exc


def _real(task: NewTask) -> NewTask:
    """Return the task under its repo's real name, so a folder-guessed owner never files a twin (T2272)."""
    real = canonical(task.repo)
    return task if real == task.repo else replace(task, repo=real)


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

    def create(self, task: NewTask) -> tuple[str, str | None]:
        """Add the section and return (note id8, the card that holds it now; None for a repo-less note)."""
        if not task.repo:
            return self._loose(task), None
        note8 = self.add(task)
        card = self.card_of(note8, task)
        if card is None:
            msg = f"note {note8} got the task, but its card is not on the board yet"
            raise BackendError(NOT_FOUND, msg)
        return note8, card

    def _loose(self, task: NewTask) -> str:
        """Add a repo-less note through the todo CLI (MCP add_task needs a repo); triage files it (T2347)."""
        body = self._linked(task)
        try:
            return create_umbrella("\n\n".join([f"# {task.title}", body]).strip(), by="kuhy")[:8]
        except MergeError as exc:
            raise BackendError(UPSTREAM, exc.message) from exc

    def _linked(self, task: NewTask) -> str:
        """Write the task's images and staged files to a fresh folder; return the body with their links."""
        pictures = _pictures(task)
        staged = uploads.claim(task.files, uploads.root())
        if isinstance(staged, str):
            raise BackendError(BAD, staged)
        folder = self._folder() if task.images or staged else ""
        # The uploads stay staged: the next picked repo claims the same ids (T2399).
        paths = noteimages.write(pictures, images.root() / folder, "")
        links = [f"[Image #{n}]\n![]({images.URL}/{folder}/{p.name})" for n, p in enumerate(paths, 1)]
        links += images.attach(staged, images.root(), folder)
        return "\n\n".join([task.body, *links]).strip()

    def add(self, task: NewTask) -> str:
        """Add the section and return its note id8; two parts may share a title (T2482)."""
        task = _real(task)
        try:
            note = self._client.add_task(task.repo, task.title, self._linked(task))
        except TodoError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
        return note.id[:8]

    def card_of(self, note8: str, task: NewTask) -> str | None:
        """Return the card holding the section: the snapshot, else fresh reads of its repo; None if never.

        Never the in-flight board fetch, which may predate the add (T2046): a read of the repo alone.
        """
        task = _real(task)
        for attempt in range(_LOOKUPS + 1):
            if attempt > 1:
                time.sleep(_PAUSE_S)
            if attempt:
                try:
                    self._cache.refresh_repo(task.repo)
                except TodoError as exc:
                    raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
            snap = self._cache.snapshot().tasks
            card = next((c.id for c in snap if _holds(c, note8, task.title)), None)
            if card is not None:
                return card
        return None

    def adopt(self, task: NewTask, key: str) -> tuple[str, str] | None:
        """Return (note id8, card) of the open section this very task became before (`key` in its body).

        A handoff rerun after a half-finished one finds its own task here (T2047), by the key alone: titles
        may repeat (T2482). None when there is none (or its card never shows). One repo listing, so a batch
        does not pay one per check.
        """
        task = _real(task)
        try:
            notes = self._client.list_tasks(repo=task.repo, full=True)
        except TodoError as exc:
            raise BackendError(UPSTREAM, upstream_text(str(exc))) from exc
        own = next(
            ((n, c) for n in notes for c in card_tasks(n) if c.status != "done" and key in c.body), None
        )
        if own is None:
            return None
        note8 = own[0].id[:8]
        card = self.card_of(note8, replace(task, title=own[1].title))
        return None if card is None else (note8, card)
