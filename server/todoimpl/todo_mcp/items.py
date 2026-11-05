"""Items: a note's `## title` sections, done-marked in the body as `## [x] title` + `closed: ...`."""

from __future__ import annotations

import re
from dataclasses import dataclass

from todoimpl.todo_mcp.model import Task

_HEADING = re.compile(r"^## (?!#)(\[x\] )?(.*)$")
_CHECK = re.compile(r"^done_check:\s*`?(.*?)`?\s*$", re.IGNORECASE)
_FENCE = "```"


@dataclass(frozen=True)
class Item:
    """One section of a note; `index` is its 0-based position among the note's sections."""

    note_id: str
    index: int
    title: str
    body: str
    repo: str | None
    status: str
    done_check: str | None


@dataclass(frozen=True)
class Section:  # noqa: D101
    heading: int
    title: str
    done: bool
    lines: list[str]


def sections(body: str) -> list[Section]:
    """Level-2 headings outside code fences; text before the first one belongs to no section."""
    found: list[Section] = []
    fenced = False
    for number, line in enumerate(body.split("\n")):
        if line.lstrip().startswith(_FENCE):
            fenced = not fenced
        match = None if fenced else _HEADING.match(line)
        if match:
            found.append(Section(number, match.group(2).strip(), bool(match.group(1)), []))
        elif found:
            found[-1].lines.append(line)
    return found


def split_items(task: Task) -> list[Item]:
    """One Item per section; a note without sections is a single Item for the whole note."""
    parts = sections(task.body)
    if not parts:
        return [Item(task.id, 0, task.title, task.body, task.repo, task.status, task.done_check)]
    items = []
    for index, part in enumerate(parts):
        lines = [line for line in part.lines if not (part.done and line.startswith("closed:"))]
        own = next((m.group(1) for line in lines if (m := _CHECK.match(line.strip()))), None)
        check = own or (task.done_check if len(parts) == 1 else None)
        status = "done" if part.done else task.status
        items.append(Item(task.id, index, part.title, "\n".join(lines).strip(), task.repo, status, check))
    return items


def mark_done(body: str, index: int, evidence: str) -> str:
    """Rewrite section `index`'s heading to `## [x] title` and add the `closed:` line."""
    lines = body.split("\n")
    part = sections(body)[index]
    lines[part.heading : part.heading + 1] = [f"## [x] {part.title}", f"closed: {' '.join(evidence.split())}"]
    return "\n".join(lines)
