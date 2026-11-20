"""Which cards run now, and since when each one has shown no real activity (T2402).

A card runs while its turn's claude is alive (`turn.pid`). Real activity is the card's own `activity` events
(tool calls, text, results) in `events.jsonl`, and the newest line of the turn's stream file when it
is a tool result or an assistant message (thinking included, T2418); the board's `system` lines,
claude's other stream lines or a touched file are not, so nothing can look alive by pinging.
A fresh turn counts from its start (the time in its stem),
not from the last cycle's events.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from todoimpl.runner import orphans

EVENTS = "events.jsonl"
CARD = re.compile(r"^[0-9a-f]{8}-\d+$")
TAIL = 256 * 1024  # bytes read from the end of events.jsonl: a long tool burst still holds a non-system line
OUTPUT = frozenset({"assistant", "user"})  # stream lines that are real work: a message, or a tool's result
BOARD_TAIL = 64 * 1024  # the board polls every running card, so it reads less than the watch does


@dataclass(frozen=True)
class Running:
    """A card whose turn is live: `since` is its last real activity, `pid` its claude."""

    card: str
    run_dir: Path
    since: float
    pid: int


def last_activity(path: Path, tail: int = TAIL) -> float | None:
    """Return the time of the newest non-`system` activity event in the last `tail` bytes, None when none."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - tail))
            data = fh.read()
    except OSError:
        return None
    for line in reversed(data.splitlines()):
        try:
            row = json.loads(line)
        except ValueError:  # the first, cut line of the tail, or a half-written last one
            continue
        if not isinstance(row, dict) or row.get("type") != "activity" or row.get("kind") == "system":
            continue
        at = row.get("at")
        if isinstance(at, int | float) and not isinstance(at, bool):
            return float(at)
    return None


def last_output(run_dir: Path, stem: str | None) -> float | None:
    """Return when claude wrote its turn's last stream line, if that line is a tool result or a message."""
    path = run_dir / f"{stem}.stream.jsonl"
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - BOARD_TAIL))
            lines = fh.read().splitlines()
            at = os.fstat(fh.fileno()).st_mtime
    except OSError:
        return None
    try:
        row = json.loads(lines[-1]) if lines else None
    except ValueError:  # claude is mid-write
        return None
    return at if isinstance(row, dict) and row.get("type") in OUTPUT else None


def card_activity(root: Path, card: str) -> float | None:
    """Return a card's last real activity from a short tail of its events (the board polls it, T2404)."""
    return last_activity(root / card / EVENTS, BOARD_TAIL)


def _stem_time(stem: str | None) -> float | None:
    """Return the launch time a turn's stem carries (`implement-1795198541.140`), None when it has none."""
    try:
        return float(str(stem).rsplit("-", 1)[1])
    except IndexError, ValueError:
        return None


def running(root: Path) -> list[Running]:
    """Return every top-level card with a live turn and the time of its last real activity."""
    found: list[Running] = []
    for run_dir in sorted(root.iterdir()) if root.is_dir() else []:
        if not CARD.match(run_dir.name) or (rec := orphans.read(run_dir)) is None or rec.pid is None:
            continue
        if not orphans.alive(rec.pid, rec.start):
            continue
        own = (last_activity(run_dir / EVENTS), _stem_time(rec.stem), last_output(run_dir, rec.stem))
        times = [t for t in own if t is not None]
        if times:
            found.append(Running(run_dir.name, run_dir, max(times), rec.pid))
    return found
