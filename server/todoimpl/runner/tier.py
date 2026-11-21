"""The cheap tier (DOCS-tiers.md): which notes are cheap, and the ESCALATE line a manager turn ends with."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from todoimpl.repotask.model import Part

CHEAP_LINE = re.compile(r"^[ \t]*tier:[ \t]*cheap[ \t]*$", re.IGNORECASE | re.MULTILINE)
CHEAP_TITLE = re.compile(r"text-free\s*\(textgate-rework\)", re.IGNORECASE)
TICKET_LINE = re.compile(r"^[ \t]*Error-Signature:", re.MULTILINE)  # an app error ticket (errors/ticket.py)
ESCALATE_LINE = re.compile(r"^[ \t]*ESCALATE:[ \t]*(.*?)[ \t]*$", re.IGNORECASE | re.MULTILINE)
REASON_MAX = 300
NO_REASON = "no reason given"
MANAGER_MODEL = "opus"  # kuhy, 2026-11-10: the free-worker manager is Opus, not Sonnet
MANAGER_EFFORT = "medium"
ESCALATED_EFFORT = "high"  # escalation = more thought on the same model


def is_cheap(title: str, body: str, parts: Iterable[Part] = ()) -> bool:
    """Say whether a note runs on the cheap tier: a `Tier: cheap` line, or the text-free rework title.

    A repo card's title is the repo name; the rework title lives in its parts (T1999), so the title of
    any part the run works counts like the card title. One cheap part makes the card cheap, as a
    `Tier: cheap` line in any part's text already did.
    """
    if TICKET_LINE.search(body):  # error fixes never go to free models (kuhy, 2026-11-21, T2445)
        return False
    titles = (title, *(part.title for part in parts if part.actionable))
    return CHEAP_LINE.search(body) is not None or any(CHEAP_TITLE.search(t) for t in titles)


def escalation(text: str) -> str | None:
    """Return the reason of the `ESCALATE: <reason>` line a turn ends with, None when it has none."""
    found = ESCALATE_LINE.search(text)
    return None if found is None else (found.group(1) or NO_REASON)[:REASON_MAX]
