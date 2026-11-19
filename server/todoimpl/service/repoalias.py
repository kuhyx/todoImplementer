"""One name per real repo: its checkout's origin, never an owner guessed from a folder name (T2272).

A note filed as `kuhyx/cleanup-plate` (feedback_inbox names a game's repo `kuhyx/<folder>`) runs in
~/src/cleanup-plate, whose origin is `Sepci0/cleanup-plate`: the board shows and groups it under the origin,
and the open note's repo field is rewritten through the todo MCP so the per-repo reads (`list_tasks(repo=)`)
find it under the real name too.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import TYPE_CHECKING

from todoimpl.board.repos import canonical
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from todoimpl.todo_mcp.client import TodoClient
    from todoimpl.todo_mcp.model import Task

    from .cards import CardTask

log = logging.getLogger("todoimpl.service")


def heal(client: TodoClient, notes: list[Task]) -> list[Task]:
    """Return the notes under their real repo; a note filed under another spelling is rewritten once.

    Case too: the todo app's repo filter is exact. A failed write keeps the real name on the board and is
    tried again on the next fetch.
    """
    out: list[Task] = []
    for note in notes:
        real = canonical(note.repo) if note.repo else None
        if real is None or real == note.repo:
            out.append(note)
            continue
        try:
            client.update_task(note.id[:8], repo=real)
        except TodoError as exc:
            log.warning("note %s repo %s -> %s not saved: %s", note.id[:8], note.repo, real, exc)
        out.append(replace(note, repo=real))
    return out


def card(found: CardTask) -> CardTask:
    """Return the card under its repo's real name (the card and its item)."""
    real = canonical(found.repo) if found.repo else found.repo
    if real == found.repo:
        return found
    return replace(found, repo=real, item=replace(found.item, repo=real))
