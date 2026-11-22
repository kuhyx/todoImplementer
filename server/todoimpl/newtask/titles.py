"""A new task's title: its first line of real text, never an `[Image #N]` placeholder (T2481).

The page (`web/src/lib/newtask-api.ts` `splitNote`) and the app (`new_task_sheet.dart` `splitNote`) split the
description box the same way; the server runs it again on what arrives (`retitle`), so an older client's
`[Image #1]` title is fixed too. A line with refs is cleaned (refs out, spaces folded); lines of refs only are
skipped. When a skipped or cleaned line held a ref, the body keeps the whole text, so no ref is lost. A note
with no text at all keeps its first line, e.g. `[Image #1]`.
"""

from __future__ import annotations

import re
from typing import Final

REF: Final = re.compile(r"\[Image #\d+\]")


def _clean(line: str) -> str:
    """Return the line's text with its image refs taken out."""
    return " ".join(REF.sub(" ", line).split()) if REF.search(line) else line.strip()


def split(text: str, cap: int) -> tuple[str, str]:
    """Return (title, body) of a description box; the title is cut to `cap` characters."""
    whole = text.strip()
    lines = whole.split("\n")
    at = next((i for i, line in enumerate(lines) if _clean(line)), None)
    if at is None:  # no text at all: the first line names it
        at, title, lossy = 0, lines[0].strip(), False
    else:
        title = _clean(lines[at])
        lossy = title != lines[at].strip() or any(line.strip() for line in lines[:at])
    if len(title) > cap:
        return title[:cap].strip(), whole
    return title, whole if lossy else "\n".join(lines[at + 1 :]).strip()


def retitle(title: str, body: str, cap: int) -> tuple[str, str]:
    """Return a client's (title, body) split again by the rule above; a split by it already stays as is."""
    return split(f"{title}\n{body}", cap)
