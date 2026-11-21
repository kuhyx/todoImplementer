"""The hash of a plan criterion's text, which keys kuhy's approve to what he saw (T2462).

The server stamps it on his click (asks/service.py); the runner accepts the approve while the criterion still
hashes the same, however often the session rewrites the rest of plan.md. The id prefix (`C20.`,
`C21 [part]:`), the `(kuhy)` marker and the line wrapping are not part of the text: a re-wrap keeps the
approve, a changed word does not.
"""

from __future__ import annotations

import hashlib
import re
from typing import TYPE_CHECKING

from .parsing import BULLET, CRITERIA_HEADING

if TYPE_CHECKING:
    from pathlib import Path

ASK_ID = re.compile(r"^c(\d+)$", re.IGNORECASE)
PREFIX = re.compile(r"^\s*(?:[-*]|\d+[.)]|C\d+(?:\s*\[[\w-]+\])?[.:)])\s+", re.IGNORECASE)
MARK = re.compile(r"^\s*\(kuhy\)\s*", re.IGNORECASE)


def blocks(plan: str) -> list[str]:
    """Return each criterion with its wrapped lines, in the order `parsing.parse_criteria` numbers them."""
    found: list[str] = []
    inside = False
    for line in plan.splitlines():
        if line.lstrip().startswith("#"):
            inside = bool(CRITERIA_HEADING.match(line.strip()))
        elif inside and BULLET.match(line):
            found.append(line)
        elif inside and found and line.strip():
            found[-1] += "\n" + line
    return found


def normalise(text: str) -> str:
    """Return the criterion's words alone: no id prefix, no `(kuhy)` marker, single spaces."""
    return " ".join(MARK.sub("", PREFIX.sub("", text, count=1), count=1).split())


def digest(text: str) -> str:
    """Return the hash stored with kuhy's answer."""
    return hashlib.sha256(normalise(text).encode()).hexdigest()[:16]


def for_ask(plan: str, ask_id: str) -> str | None:
    """Return the hash of the criterion the ask is about, or None when the plan names none.

    Ask `cN` is criterion N. Any other ask is the review of the plan's only `(kuhy)` criterion when there is
    exactly one (approval.py's sole fallback).
    """
    found = blocks(plan)
    if (match := ASK_ID.match(ask_id)) is not None:
        n = int(match.group(1))
        return digest(found[n - 1]) if 0 < n <= len(found) else None
    marked = [text for text in found if MARK.match(PREFIX.sub("", text, count=1))]
    return digest(marked[0]) if len(marked) == 1 else None


def from_file(plan_md: Path, ask_id: str) -> str | None:
    """Return `for_ask` on the run's plan.md, or None when it cannot be read."""
    try:
        return for_ask(plan_md.read_text(encoding="utf-8"), ask_id)
    except OSError:
        return None
