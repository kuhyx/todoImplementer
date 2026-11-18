"""``GET /api/sessions``: every interactive (manually started) session, open ones first.

Also the lookup the session mutations use, so that "is this id real, and
where does it live?" is answered from the same scan the user is looking at,
never from the request.
"""

from __future__ import annotations

import os
import time
import uuid
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Any

from todoimpl.sessions import movable
from todoimpl.sessions.markstore import read_marks
from todoimpl.sessions.scan import Scanner
from todoimpl.tokens_api import paths

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.sessions.commands import CommandRunner
    from todoimpl.sessions.parse import Session

__all__ = ["SCANNER", "Scanner", "canonical_id", "find", "listing", "marks_path", "projects_dir"]

# One process-wide cache: GETs and mutations share it, so a resume right after
# a page load re-reads nothing.
SCANNER = Scanner()
# Open sessions in the order they need attention; everything done after them.
# `group` is that rank, sent with every row so the page sorts on it and never computes status itself.
_GROUP = {"needs_action": 0, "question": 1, "untagged": 2, "running": 3}
_DONE_GROUP = len(_GROUP)
_DONE_STATUSES = frozenset({"done", "continuing"})


def projects_dir() -> Path:
    """Where Claude Code keeps one directory of transcripts per project."""
    return paths.user_path(".claude/projects")


def marks_path() -> Path:
    """Return the manual-mark store path, next to Claude Code's own state."""
    return paths.user_path(".claude/session-status.json")


def canonical_id(value: object) -> str | None:
    """Return ``value`` if it is a UUID in canonical form, else None.

    ``uuid.UUID`` alone also accepts braces, ``urn:uuid:``, upper case and
    no hyphens; only the spelling Claude Code writes is an id here, because
    the id ends up inside a shell command line.
    """
    if not isinstance(value, str):
        return None
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        return None
    return value if str(parsed) == value else None


def find(session_id: str) -> Session | None:
    """Look an id up in a (warm, cheap) rescan of the transcripts."""
    return SCANNER.scan(projects_dir())[0].get(session_id)


def _quote(text: str) -> str:
    """Single-quote for a POSIX shell, always, as the contract shows."""
    return "'" + text.replace("'", "'\\''") + "'"


def _project(cwd: str) -> str:
    """Return the short project name: the cwd's basename, or ``~`` for home."""
    home = os.environ.get("HOME", "").rstrip("/")
    if cwd.rstrip("/") == home:
        return "~"
    return PurePosixPath(cwd.rstrip("/")).name


def _row(runner: CommandRunner, session: Session, mark: dict[str, Any] | None) -> dict[str, Any]:
    """Render one session in the frontend's JSON contract."""
    manual = mark.get("mark") if mark else None
    done = session.status in _DONE_STATUSES or manual == "done"
    _, move_reason = movable.verdict(runner, session, manual)
    return {
        "id": session.id,
        "cwd": session.cwd,
        "project": _project(session.cwd),
        "title": session.title,
        "status": session.status,
        "done": done,
        "group": _DONE_GROUP if done else _GROUP.get(session.status, 0),
        "mark": "manual" if manual == "done" else ("tag" if done else "open"),
        "manual_mark": manual,
        "last_ts": session.last_ts,
        "last_user": session.last_user,
        "last_assistant": session.last_assistant,
        "resume_command": f"cd {_quote(session.cwd)} && claude --resume {session.id}",
        "movable": move_reason is None,
        "move_reason": move_reason,
    }


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Group by urgency, newest first within each group."""
    rows = sorted(rows, key=lambda r: r["last_ts"] or "", reverse=True)
    return sorted(rows, key=lambda r: r["group"])


def listing(runner: CommandRunner) -> dict[str, Any]:
    """Return the whole session list with the scan's cost (the GET body); `runner` asks git for repos."""
    started = time.perf_counter()
    sessions, scanned = SCANNER.scan(projects_dir())
    marks = read_marks(marks_path())
    rows = _ordered([_row(runner, s, marks.get(s.id)) for s in sessions.values()])
    elapsed = (time.perf_counter() - started) * 1000
    return {"sessions": rows, "scanned": scanned, "scan_ms": round(elapsed, 1)}
