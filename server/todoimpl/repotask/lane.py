"""Who asked for a part: kuhy, the board itself, or another app's error report (T2580, kuhy 2026-11-27).

kuhy's rule: "tasks requested by the USER should ALWAYS take priority and start first before automatic tasks".
The lane orders parts inside a card (before priority) and cards that wait for the same thing. Other apps'
reports also count as `low` priority whatever their note says: they wait for everything else.

A merged note (an umbrella's `## kuhyx/<repo> (<key>)` children, a same-repo merge's `### <id>` members) takes
the best lane of its open members (T2592): an umbrella of kartka tickets is `app`, but one kuhy child among
them keeps it in kuhy's lane. When every member is done, all of them count.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from todoimpl.errors.marks import app_ticket, own

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .model import Part

KUHY: Final = "kuhy"  # a part kuhy wrote (no `Error-Signature:` or `Reset-Key:` line)
BOARD: Final = "board"  # the board's own: stalls, slow steps, heavy builds, no-limit reds, token optimization
APP: Final = "app"  # other apps' error reports (kartka, book-guard, ...)
ORDER: Final = (KUHY, BOARD, APP)
LOWEST: Final = "low"
SECTION: Final = re.compile(
    r"^(?:## (?P<done>\[x\] )?kuhyx/[\w.-]+ \([A-Za-z0-9]{8}(?:-\d+)?\)|### [0-9a-f]{8}(?:-\d+)?)[ \t]*$",
    re.MULTILINE,
)


def _one(text: str) -> str:
    if app_ticket(text):
        return APP
    return BOARD if own(text) else KUHY


def of_text(text: str) -> str:
    """Return the lane of one part's (or one plain note's) text; a merged note's is its best open member's."""
    heads = list(SECTION.finditer(text))
    if not heads:
        return _one(text)
    ends = [h.start() for h in heads[1:]] + [len(text)]
    members = [(h["done"] is not None, text[h.end() : end]) for h, end in zip(heads, ends, strict=True)]
    found = [body for done, body in members if not done] or [body for _, body in members]
    return min((_one(body) for body in found), key=rank)


def rank(name: str) -> int:
    """Return the sort rank of a lane: kuhy's first."""
    return ORDER.index(name)


def priority(note_priority: str, text: str) -> str:
    """Return a part's priority: its note's, but other apps' reports are always the lowest."""
    return LOWEST if of_text(text) == APP else note_priority


def first(parts: Iterable[Part], body: str) -> str:
    """Return the lane a card's run starts with: the best of its work parts, else its own text."""
    found = [of_text(part.body) for part in parts if part.actionable]
    return min(found, key=rank) if found else of_text(body)


def of_card(card: object) -> str:
    """Return a card's lane (a CardTask or TaskLike): the first part its run works, a plain note its text."""
    return first(getattr(card, "parts", ()) or (), str(getattr(card, "body", "")))
