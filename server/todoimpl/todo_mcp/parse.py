"""Parsers for the todo server's plain-text tool results (list lines, task detail, add reply)."""

from __future__ import annotations

import re

from todoimpl.todo_mcp.model import Task, TodoError

ID_LEN = 8
_STATUS_FROM_WIRE = {"todo": "todo", "in_progress": "in progress", "done": "done", "abandoned": "abandoned"}
_LIST_FIELDS = 5
_NO_TASKS = "no tasks match"
_ADDED = re.compile(r"^(?:added|appended to) (\S+)")


def to_wire(status: str) -> str:
    """Spell a status the way the server does (``in progress`` becomes ``in_progress``)."""
    return status.replace(" ", "_")


def _status(wire: str) -> str:
    if wire not in _STATUS_FROM_WIRE:
        msg = f"unknown task status {wire!r} in server reply"
        raise TodoError(msg)
    return _STATUS_FROM_WIRE[wire]


def parse_list(text: str) -> list[Task]:
    r"""Parse ``<id8>\\t<status>\\t<priority>\\t<repo or ->\\t<title>`` lines."""
    if text.strip() == _NO_TASKS:
        return []
    tasks: list[Task] = []
    for line in text.split("\n"):
        parts = line.split("\t")
        if len(parts) != _LIST_FIELDS:
            msg = f"malformed list line: {line[:80]!r}"
            raise TodoError(msg)
        task_id, status, priority, repo, title = parts
        tasks.append(
            Task(task_id[:ID_LEN], title, "", None if repo == "-" else repo, _status(status), priority, None)
        )
    return tasks


def parse_detail(text: str) -> Task:
    """Parse ``get_task``: ``key: value`` lines, ``---``, then the note text (title, blank, body)."""
    head, sep, note = text.partition("\n---\n")
    meta = dict(line.split(": ", 1) for line in head.split("\n") if ": " in line)
    if not sep or not {"id", "status", "priority"} <= meta.keys():
        msg = f"malformed task detail: {text[:80]!r}"
        raise TodoError(msg)
    title, _, body = note.strip().partition("\n")
    return Task(
        meta["id"][:ID_LEN],
        title.lstrip("#").strip(),
        body.strip(),
        meta.get("repo"),
        _status(meta["status"]),
        meta["priority"],
        meta.get("done_check"),
    )


def added_id(text: str) -> str:
    """Extract the 8-char id from ``added <id>`` or ``appended to <id>``."""
    match = _ADDED.match(text)
    if match is None:
        msg = f"malformed add_task reply: {text[:80]!r}"
        raise TodoError(msg)
    return match.group(1)[:ID_LEN]
