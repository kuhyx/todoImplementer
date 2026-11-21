"""Which cards run now, and since when each one has shown no real activity (T2402).

A card runs while its turn's claude is alive (`turn.pid`). Real activity is the card's own `activity` events
(tool calls, text, results) in `events.jsonl`, and the newest tool result or assistant message
line of the turn's stream file (thinking included, T2418), at that line's own time (T2447); the
board's `system` lines, claude's other stream lines or a touched file are not, so nothing can look alive by
pinging. An advisor call waiting on its answer is work for a while (T2448).
A fresh turn counts from its start (the time in its stem),
not from the last cycle's events.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from todoimpl.runner import orphans

EVENTS = "events.jsonl"
CARD = re.compile(r"^[0-9a-f]{8}-\d+$")
TAIL = 256 * 1024  # bytes read from the end of events.jsonl: a long tool burst still holds a non-system line
OUTPUT = frozenset({"assistant", "user"})  # stream lines that are real work: a message, or a tool's result
BOARD_TAIL = 64 * 1024  # the board polls every running card, so it reads less than the watch does
ADVISOR = (
    240.0  # s an unanswered advisor call counts as work: it answers in 60-140 s, nothing streams meanwhile
)


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


def _stamp(row: dict[str, object]) -> float | None:
    """Return the epoch time of a stream line's ISO `timestamp`, None when it has none."""
    try:
        return datetime.fromisoformat(str(row["timestamp"])).timestamp()
    except KeyError, ValueError:
        return None


def _pending_advisor(row: dict[str, object]) -> bool:
    """Tell whether a message line ends on a server tool call (the advisor) whose answer has not come."""
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    last = content[-1] if isinstance(content, list) and content else None
    return isinstance(last, dict) and last.get("type") == "server_tool_use"


def last_output(run_dir: Path, stem: str | None) -> float | None:
    """Return when claude wrote its turn's newest message or tool result line (T2447).

    claude writes `system` lines (task_*, thinking_tokens) right after a result, so the walk skips them and
    any torn line and reads the line's own `timestamp`; a line without one counts only as the file's last
    line (its mtime). An advisor call still waiting on its answer counts for `ADVISOR` s more (T2448).
    """
    path = run_dir / f"{stem}.stream.jsonl"
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - BOARD_TAIL))
            lines = fh.read().splitlines()
            mtime = os.fstat(fh.fileno()).st_mtime
    except OSError:
        return None
    for back, line in enumerate(reversed(lines)):
        try:
            row = json.loads(line)
        except ValueError:  # claude is mid-write, or the tail cut the line
            continue
        if not isinstance(row, dict) or row.get("type") not in OUTPUT:
            continue
        at = _stamp(row)
        if at is None:
            return mtime if back == 0 else None
        return at + ADVISOR if _pending_advisor(row) else at
    return None


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
