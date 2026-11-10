"""The cheap tier (DOCS-tiers.md): which notes are cheap, and the ESCALATE line a manager turn ends with."""

from __future__ import annotations

import re

CHEAP_LINE = re.compile(r"^[ \t]*tier:[ \t]*cheap[ \t]*$", re.IGNORECASE | re.MULTILINE)
CHEAP_TITLE = re.compile(r"text-free\s*\(textgate-rework\)", re.IGNORECASE)
ESCALATE_LINE = re.compile(r"^[ \t]*ESCALATE:[ \t]*(.*?)[ \t]*$", re.IGNORECASE | re.MULTILINE)
REASON_MAX = 300
NO_REASON = "no reason given"
MANAGER_MODEL = "sonnet"


def is_cheap(title: str, body: str) -> bool:
    """Say whether a note runs on the cheap tier: a `Tier: cheap` line, or the text-free rework title."""
    return CHEAP_LINE.search(body) is not None or CHEAP_TITLE.search(title) is not None


def escalation(text: str) -> str | None:
    """Return the reason of the `ESCALATE: <reason>` line a turn ends with, None when it has none."""
    found = ESCALATE_LINE.search(text)
    return None if found is None else (found.group(1) or NO_REASON)[:REASON_MAX]
