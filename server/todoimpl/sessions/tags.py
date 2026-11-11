"""Pure record readers: what a user typed, what Claude said, which tag it ended on.

No I/O here, so the rules that decide a session's status are testable on
dicts alone.
"""

from __future__ import annotations

import re
from typing import Any

# Status tag lines, read the way ~/.claude/hooks/status_tag_stop.py
# (TAG_LINE) reads them: a long form or one letter (D/R/Q/A/C, since
# 2026-11-01) at line start, its colon right after it (bold allowed), after
# optional quote, list, heading or emphasis marks. Keep the two in step.
_TAG_LINE = re.compile(
    r"^[\s>*_#-]*(?:(DONE|RUNNING|QUESTION|NEEDS ACTION)[*_]*\s*|([DRQAC])[*_]*):",
    re.MULTILINE,
)
_LONG = {
    "DONE": "done",
    "NEEDS ACTION": "needs_action",
    "QUESTION": "question",
    "RUNNING": "running",
}
_SHORT = {
    "D": "done",
    "A": "needs_action",
    "Q": "question",
    "R": "running",
    "C": "continuing",
}
_CONTINUING = "continuing in new session"
# A handoff outranks "done", which outranks anything still open.
_PRECEDENCE = ("continuing", "done", "needs_action", "question", "running")
UNTAGGED = "untagged"

# User-role content the harness wrote, not the user: slash-command wrappers,
# `!cmd` echoes, background-task notifications and injected reminders. Counted
# as prompts they would mark every session with a background agent as
# "interrupted", and title sessions "<task-notification>".
_GENERATED_PREFIXES = (
    "<command-",
    "<local-command",
    "<bash-",
    "<task-notification",
    "<system-reminder",
    "<user-prompt-submit-hook",
)
# Flags on user records that mean "synthetic": meta caveats, the summary a
# compaction writes, and subagent traffic.
_SYNTHETIC_FLAGS = ("isMeta", "isCompactSummary", "isSidechain")


def classify(text: str) -> str:
    """Return the status a final assistant message ends on.

    Every line is scanned, because the tag is often followed by an ``N:``
    note line. "continuing in new session" counts anywhere, any case.
    """
    found = {_LONG[long] if long else _SHORT[short] for long, short in _TAG_LINE.findall(text)}
    if _CONTINUING in text.lower():
        found.add("continuing")
    return next((status for status in _PRECEDENCE if status in found), UNTAGGED)


def _is_generated(text: str) -> bool:
    """Whether a text block is harness output rather than something typed."""
    return text.lstrip().startswith(_GENERATED_PREFIXES)


def _content(record: dict[str, Any]) -> object:
    """Return the message content of a record, or None when it has no message."""
    message = record.get("message")
    return message.get("content") if isinstance(message, dict) else None


def prompt_text(record: dict[str, Any]) -> str | None:
    """Return what the user typed in this record, or None if it is not a prompt.

    Tool results, meta records and harness wrappers are all user-role records
    that nobody typed; none of them count.
    """
    if any(record.get(flag) for flag in _SYNTHETIC_FLAGS):
        return None
    content = _content(record)
    if isinstance(content, str):
        return None if _is_generated(content) else content.strip()
    if not isinstance(content, list):
        return None
    texts = [
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    ]
    typed = [t.strip() for t in texts if t.strip() and not _is_generated(t)]
    if typed:
        return "\n".join(typed)
    has_image = any(isinstance(b, dict) and b.get("type") == "image" for b in content)
    return "[image]" if has_image else None


def assistant_text(record: dict[str, Any]) -> str | None:
    """Join an assistant record's text blocks; None if it has none.

    One API message is split across several records (thinking, text,
    tool_use), so a record with no text block is normal and simply skipped.
    """
    content = _content(record)
    if not isinstance(content, list):
        return None
    texts = [
        block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
    ]
    return "\n".join(texts) if texts else None
