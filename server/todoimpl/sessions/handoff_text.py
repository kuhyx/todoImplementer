"""The board task a stalled session becomes: its `## title` and a body in the note template's sections.

The body is appended under `## <title>` in the repo's todo note, where every `## ` line starts another card
(`todo_mcp/items.py`), a ``` line opens a fence and a `done_check:` line sets the check. So the sections are
`### ` headings, and kuhy's own text (prompt, reply) is quoted line by line, which leaves all three inert.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.http.newtask import MAX_TITLE

if TYPE_CHECKING:
    from todoimpl.sessions.parse import Session


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _quoted(text: str) -> str:
    """Quote every line, so no line of it can start a heading, a fence or a check."""
    lines = text.strip().splitlines() or [""]
    return "\n".join(f"> {line}".rstrip() for line in lines)


def title(session: Session) -> str:
    """Return the title on one line, at most MAX_TITLE characters, never a done mark, never empty."""
    text = _one_line(session.title).removeprefix("[x] ").strip() or f"Session {session.id[:8]}"
    return text if len(text) <= MAX_TITLE else text[: MAX_TITLE - 1] + "…"


def body(session: Session) -> str:
    """Return what the headless session needs to pick the work up where the manual one stopped."""
    return "\n".join(
        [
            "### what",
            f"Finish the manual Claude Code session {session.id}, which stalled: {_one_line(session.title)}",
            "",
            "Last prompt:",
            _quoted(session.last_user),
            "",
            "### where",
            _one_line(session.cwd),
            "",
            "### done",
            "Read the transcript and finish the work it left open.",
            "",
            "### verify",
            "Verify the result the way the repo's CLAUDE.md says.",
            "",
            "### read first",
            f"- {_one_line(session.path)}",
            "",
            "last reply:",
            _quoted(session.last_assistant),
        ]
    )
