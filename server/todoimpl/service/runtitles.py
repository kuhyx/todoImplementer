"""Titles for run dirs no board card or part names any more, so /api/usage never shows a bare id (T1996).

A run dir `<note8>-<n>` outlives its card: the note closed, or its sections became parts of a repo card. The
note is still in the todo app, so its section `n` (else the note) names the run. Notes are fetched on the
cache thread, a few per round, once each; the usage request only reads the memo.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.todo_mcp.items import split_items

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable
    from pathlib import Path

    from todoimpl.todo_mcp.client import TodoClient

    from .cards import CardTask

log = logging.getLogger("todoimpl.service")
LABELS = frozenset(
    {
        "what",
        "why",
        "how",
        "goal",
        "context",
        "problem",
        "fix",
        "note",
        "notes",
        "todo",
        "summary",
        "details",
        "background",
        "idea",
        "task",
        "description",
        "desc",
    }
)
SHORT = 80
PER_ROUND = 6  # notes fetched per refresh: a first start with 40 stale run dirs must not stall the board
RETRY = 600.0  # seconds before a note that could not be fetched is asked for again
_SENTENCE = re.compile(r"(?<=[.!?])\s")


def best_title(title: str, body: str) -> str:
    """Return the title, or the body's first sentence when the title is a bare label such as "What"."""
    text = " ".join(title.split())
    if text.lower().rstrip(":") not in LABELS:
        return text
    lines = [line.strip() for line in body.split("\n") if line.strip() and not line.lstrip().startswith("#")]
    first = _SENTENCE.split(lines[0], maxsplit=1)[0] if lines else ""
    if len(first) > SHORT:
        return first[: SHORT - 1].rstrip() + "…"
    return first or text


def card_titles(cards: Iterable[CardTask]) -> dict[str, str]:
    """Return card id and part key -> title of the board cards (a card's own title wins over a part's)."""
    found: dict[str, str] = {}
    for card in cards:
        found.update({part.key: best_title(part.title, part.body) for part in card.parts})
    found.update({card.id: best_title(card.title, card.body) for card in cards})
    return found


class RunTitles:
    """Memo of run id -> title, read from the todo app for the run dirs the board no longer shows."""

    def __init__(self, client: TodoClient, root: Path, clock: Callable[[], float] = time.monotonic) -> None:
        """`root` is the run root holding one `<note8>-<n>` dir per item."""
        self._client = client
        self._root = root
        self._clock = clock
        self._titles: dict[str, str] = {}
        self._retry: dict[str, float] = {}
        self._lock = threading.Lock()

    def titles(self) -> dict[str, str]:
        """Return a copy of what is known so far."""
        with self._lock:
            return dict(self._titles)

    def update(self, known: Collection[str]) -> None:
        """Fetch the notes of a few run dirs that neither `known` (card and part ids) nor the memo name."""
        wanted: dict[str, list[str]] = {}
        names = sorted(d.name for d in self._root.iterdir()) if self._root.is_dir() else []
        now = self._clock()
        with self._lock:
            for name in names:
                note, _, index = name.rpartition("-")
                fresh = name not in known and name not in self._titles and self._retry.get(note, 0.0) <= now
                if note and index.isdigit() and fresh:
                    wanted.setdefault(note, []).append(name)
        for note, ids in list(wanted.items())[:PER_ROUND]:
            try:
                task = self._client.get_task(note)
            except Exception as exc:  # noqa: BLE001 - a missing note must not stop the board's refresh
                log.warning("run title: note %s not fetched: %s", note, exc)
                with self._lock:
                    self._retry[note] = now + RETRY
                continue
            items = split_items(task)
            with self._lock:
                for name in ids:
                    position = int(name.rpartition("-")[2])
                    item = items[position] if position < len(items) else None
                    found = best_title(item.title, item.body) if item else best_title(task.title, "")
                    self._titles[name] = found
