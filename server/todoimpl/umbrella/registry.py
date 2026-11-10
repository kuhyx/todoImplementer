"""Umbrella notes without a repo are invisible to the todo MCP's list_tasks (it lists repo tasks only).

Two sources name them. The merge ledger (`<run root>/merge.json`, `created`) lists every note a merge made,
so an umbrella made by "Merge similar tasks" reaches the board with no step by kuhy. For one made by hand,
`~/.config/todoImplementer/umbrellas.txt` (`$TODOIMPL_UMBRELLAS`) holds one note id (8 chars or full) per
line; `#` starts a comment. A note that has a repo needs no entry. Entries that are closed, abandoned,
missing or not umbrellas are skipped (a closed umbrella stays on the board through its run dir).
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.merge.store import MergeStore
from todoimpl.todo_mcp.model import TodoError

from .note import is_umbrella

if TYPE_CHECKING:
    from todoimpl.todo_mcp.client import TodoClient
    from todoimpl.todo_mcp.model import Task

log = logging.getLogger("todoimpl.service")
OPEN = ("todo", "in progress")


def path() -> Path:
    """Return the registry file."""
    env = os.environ.get("TODOIMPL_UMBRELLAS")
    return Path(env) if env else Path.home() / ".config" / "todoImplementer" / "umbrellas.txt"


def ids(root: Path) -> list[str]:
    """Return the note ids named by the registry file and by the merge ledger under `root`."""
    try:
        lines = path().read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    made = [str(entry["id"]) for entry in MergeStore(root).load().created.values() if entry.get("id")]
    return [*(text for line in lines if (text := line.split("#", 1)[0].strip())), *made]


def notes(client: TodoClient, root: Path, listed: set[str]) -> list[Task]:
    """Return the open registered umbrella notes that `list_tasks` did not return (`listed` = their id8s)."""
    found = []
    for note_id in ids(root):
        if note_id[:8] in listed:
            continue
        try:
            task = client.get_task(note_id[:8])
        except TodoError as exc:
            log.warning("registered umbrella %s not fetched: %s", note_id, exc)
            continue
        if task.status in OPEN and is_umbrella(task.body):
            found.append(task)
    return found
