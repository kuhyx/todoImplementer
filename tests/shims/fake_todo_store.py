"""In-memory twin of the todo app's TaskService (``~/src/todo/lib/mcp/task_service.dart``).

Used by ``fake_todo_mcp`` only; tests normally touch it through ``FakeTodoMcp.store``.
Argument names, validation order, error texts and output formats match the Dart server.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

_REPO = re.compile(r"^[\w.-]+/[\w.-]+$")
_STATUSES = ("todo", "in_progress", "done", "abandoned")
_PRIORITIES = ("low", "medium", "high")
_MIN_PREFIX = 8


class ToolError(Exception):
    """A refusal: reaches the client as ``isError`` content ``error: <message>``."""


@dataclass
class FakeNote:
    """One todo-app note (``text`` = title line, blank line, body)."""

    id: str
    text: str
    priority: str = "medium"
    status: str = "todo"
    repo: str | None = None
    done_check: str | None = None
    by: str | None = None
    evidence: str | None = None
    created: str = ""
    updated: str = ""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _opt(args: dict[str, object], name: str) -> str | None:
    value = args.get(name)
    if value is None:
        return None
    if not isinstance(value, str):
        msg = f"{name}: must be a string"
        raise ToolError(msg)
    return value.strip() or None


def _req(args: dict[str, object], name: str) -> str:
    value = _opt(args, name)
    if value is None:
        msg = f"{name}: required, not blank"
        raise ToolError(msg)
    return value


def _pick(args: dict[str, object], name: str, choices: tuple[str, ...]) -> str | None:
    value = _opt(args, name)
    if value is not None and value not in choices:
        msg = f'{name}: must be one of {"|".join(choices)}, got "{value}"'
        raise ToolError(msg)
    return value


def _repo(args: dict[str, object], *, required: bool = False) -> str | None:
    if not required and "repo" not in args:
        return None
    value = _opt(args, "repo") or ""
    if not _REPO.match(value):
        msg = f'repo: must look like owner/name, got "{value}"'
        raise ToolError(msg)
    return value


def title_of(note: FakeNote) -> str:
    """First line of the note text."""
    return note.text.split("\n")[0]


def list_line(note: FakeNote) -> str:
    r"""``<id8>\\t<status>\\t<priority>\\t<repo or ->\\t<title>``."""
    return "\t".join([note.id[:_MIN_PREFIX], note.status, note.priority, note.repo or "-", title_of(note)])


def detail(note: FakeNote) -> str:
    """Metadata lines, ``---``, then the text (``noteDetail`` in note_lookup.dart)."""
    head = [f"id: {note.id}", f"priority: {note.priority}", f"status: {note.status}"]
    head += [f"created: {note.created}", f"updated: {note.updated}"]
    for key in ("repo", "done_check", "by", "evidence"):
        if (value := getattr(note, key)) is not None:
            head.append(f"{key}: {value}")
    return "\n".join([*head, "---", note.text])


def _join_checks(older: str | None, newer: str | None) -> str | None:
    if not older:
        return newer or None
    return f"( {older} ) && ( {newer} )" if newer else older


class FakeStore:
    """The six tools over a dict of notes; ``call`` raises ``ToolError`` for refusals."""

    def __init__(self) -> None:
        """Start empty."""
        self.notes: dict[str, FakeNote] = {}

    def seed(self, repo: str | None, title: str, body: str = "", **fields: str | None) -> str:
        """Insert a note directly and return its full id. ``fields`` overrides any FakeNote field."""
        text = f"{title}\n\n{body}" if body else title
        note_id = str(fields.pop("id", None) or uuid.uuid4())
        now = _now()
        note = FakeNote(note_id, text, repo=repo, created=now, updated=now)
        for key, value in fields.items():
            setattr(note, key, value)
        self.notes[note_id] = note
        return note_id

    def call(self, name: str, args: dict[str, object]) -> str:
        """Run tool ``name``; unknown names raise ``ToolError``."""
        handler = getattr(self, f"_tool_{name}", None)
        if handler is None:
            msg = f"unknown tool {name}"
            raise ToolError(msg)
        result: str = handler(args)
        return result

    def _find(self, args: dict[str, object]) -> FakeNote:
        ref = _req(args, "id")
        if ref in self.notes:
            return self.notes[ref]
        if len(ref) < _MIN_PREFIX:
            msg = f"id: no live note with id {ref} (an id prefix needs at least {_MIN_PREFIX} characters)"
            raise ToolError(msg)
        hits = [n for n in self.notes.values() if n.id.startswith(ref)]
        if len(hits) != 1:
            msg = (
                f"id: no live note with id {ref}"
                if not hits
                else f"id: id prefix {ref} matches {len(hits)} notes"
            )
            raise ToolError(msg)
        return hits[0]

    def _saved(self, note: FakeNote, verb: str) -> str:
        note.updated = _now()
        self.notes[note.id] = note
        return f"{verb} {note.id}\n{list_line(note)}"

    def _lines(self, notes: list[FakeNote]) -> str:
        return "\n".join(list_line(n) for n in notes) or "no tasks match"

    def _tool_add_task(self, args: dict[str, object]) -> str:
        repo = _repo(args, required=True) or ""
        title = _req(args, "title")
        body = _opt(args, "body") or ""
        check, prio = _opt(args, "done_check"), _pick(args, "priority", _PRIORITIES) or "medium"
        section = f"## {title}\n{body}" if body else f"## {title}"
        open_notes = [
            n for n in self.notes.values() if n.repo == repo and n.status in ("todo", "in_progress")
        ]
        if open_notes:
            note = min(open_notes, key=lambda n: (n.created, n.id))
            note.text += f"\n\n{section}"
            note.done_check = _join_checks(note.done_check, check)
            note.priority = max(note.priority, prio, key=_PRIORITIES.index)
            return self._saved(note, "appended to")
        note_id = self.seed(repo, f"{repo.split('/')[-1]} todos", section, priority=prio, by="claude")
        self.notes[note_id].done_check = check
        return self._saved(self.notes[note_id], "added")

    def _tool_list_tasks(self, args: dict[str, object]) -> str:
        repo = _repo(args)
        raw = _opt(args, "status")
        if raw not in (None, "open", "all", *_STATUSES):
            msg = f'status: must be one of {"|".join(_STATUSES)}, got "{raw}"'
            raise ToolError(msg)
        wanted = (
            {"todo", "in_progress"} if raw in (None, "open") else set(_STATUSES) if raw == "all" else {raw}
        )
        hits = [n for n in self.notes.values() if n.repo and n.status in wanted and repo in (None, n.repo)]
        return self._lines(hits)

    def _tool_search_tasks(self, args: dict[str, object]) -> str:
        query = _req(args, "query").lower()
        hits = [n for n in self.notes.values() if n.repo and query in f"{n.text} {n.repo}".lower()]
        return self._lines(hits)

    def _tool_get_task(self, args: dict[str, object]) -> str:
        return detail(self._find(args))

    def _tool_update_task(self, args: dict[str, object]) -> str:
        note = self._find(args)
        status = _pick(args, "status", _STATUSES)
        if status == "done":
            msg = "status: use close_task with evidence"
            raise ToolError(msg)
        lines = note.text.split("\n")
        title = _req(args, "title") if "title" in args else lines[0]
        body = (_opt(args, "body") or "") if "body" in args else "\n".join(lines[1:]).lstrip()
        prio, repo = _pick(args, "priority", _PRIORITIES), _repo(args)
        if "done_check" in args:
            note.done_check = _opt(args, "done_check")
        if status and note.status == "done":
            note.evidence = None
        note.text = f"{title}\n\n{body}" if body else title
        note.priority, note.status = prio or note.priority, status or note.status
        note.repo = repo or note.repo
        return self._saved(note, "updated")

    def _tool_close_task(self, args: dict[str, object]) -> str:
        evidence = _req(args, "evidence")
        note = self._find(args)
        note.status, note.evidence = "done", evidence
        return self._saved(note, "closed")
