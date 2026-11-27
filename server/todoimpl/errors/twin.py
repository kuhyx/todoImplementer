"""Ask the todo app itself before a ticket is made: one open part per signature, one per issue (T2570).

The board's cards are a cache. Right after a restart they are empty until the first fetch lands (the todo
MCP may still be down), so the loop's own lookup (`ticket.find`) can miss a part that is there. Before any
new part this module reads the repo's open notes straight from the todo app:

- an open part that already carries the signature line takes the record (no second part);
- an open part of the same app with the very same `Error:` line (kind and whole message) is the same issue
  under another signature (kartka's slow waits are signed per route): the record's block is appended to it.

A todo app that cannot answer raises `TodoError`: the caller makes nothing that tick.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.board.repos import canonical
from todoimpl.todo_mcp.items import sections, split_items
from todoimpl.todo_mcp.model import TodoError

from .marks import signatures

if TYPE_CHECKING:
    from .ports import Tasks
    from .record import AppError

ERROR = "Error: "


@dataclass(frozen=True)
class Spot:
    """An open part of the repo: its note id, item index, title and text; `same` = it has this signature."""

    note: str
    index: int
    title: str
    text: str
    same: bool


def issues(text: str) -> set[str]:
    """Return what makes two parts one issue: `<app>|<Error: line>` for each app signed in the text."""
    apps = {key.split(":", 1)[0] for key in signatures(text)}
    errors = [line.strip() for line in text.split("\n") if line.strip().startswith(ERROR)]
    return {f"{app}|{line}" for app in apps for line in errors}


def block(body: str) -> list[str]:
    """Return a ticket text from its first `Error:` line on: what a part that joins another one adds."""
    lines = body.split("\n")
    at = next((i for i, line in enumerate(lines) if line.strip().startswith(ERROR)), 0)
    return ["", *lines[at:]]


def lookup(tasks: Tasks, record: AppError, error: str) -> Spot | None:
    """Return the open part with the record's signature, else one with its issue (`error` line), else None."""
    issue = f"{record.app}|{error}"
    twin: Spot | None = None
    for note in tasks.list_tasks(repo=canonical(record.repo), full=True):
        for item in split_items(note):
            if item.status == "done":
                continue
            if record.key in signatures(item.body):
                return Spot(note.id, item.index, item.title, item.body, same=True)
            if twin is None and issue in issues(item.body):
                twin = Spot(note.id, item.index, item.title, item.body, same=False)
    return twin


def append(body: str, index: int, title: str, extra: list[str]) -> str:
    """Return the note with `extra` at the end of item `index`; TodoError when that item moved."""
    lines = body.split("\n")
    parts = sections(body)
    if not parts:
        return "\n".join([body.rstrip(), *extra])
    if index >= len(parts) or parts[index].title != title or parts[index].done:
        msg = f"part {title!r} moved or closed"
        raise TodoError(msg)
    part = parts[index]
    end = part.heading + 1 + len(part.lines)
    while end > part.heading + 1 and not lines[end - 1].strip():
        end -= 1
    return "\n".join([*lines[:end], *extra, *lines[end:]])


def attach(tasks: Tasks, spot: Spot, extra: list[str]) -> None:
    """Append `extra` to the part at `spot`, read fresh from the todo app."""
    note = tasks.get_task(spot.note)
    tasks.update_task(spot.note, body=append(note.body, spot.index, spot.title, extra))


def join(tasks: Tasks, record: AppError, body: str) -> str | None:
    """Put the record on the open part that holds it or its issue; return that part's title, None if none."""
    spot = lookup(tasks, record, block(body)[1])
    if spot is None:
        return None
    if not spot.same:
        attach(tasks, spot, block(body))
    return spot.title
