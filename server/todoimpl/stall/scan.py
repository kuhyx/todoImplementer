"""Which cards run now, and since when each one has shown no real activity (T2402).

A card runs while its turn's claude is alive (`turn.pid`). Real activity is the card's own `activity` events
(tool calls, text, results) in `events.jsonl`, and the newest tool result or assistant message
line of the turn's stream file (thinking included, T2418), at that line's own time (T2447); the
board's `system` lines, claude's other stream lines or a touched file are not, so nothing can look alive by
pinging. An advisor call waiting on its answer, on any thread, is work for a while (T2448, T2486). So are a
foreground sub-agent's own message lines, which claude keeps out of the stream (T2561). A fresh turn counts
from its start (the time in its stem), not from the last cycle's events.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from todoimpl.runner import freeworker, orphans
from todoimpl.runner.workerwait import EXIT, PID

from . import output, subagent
from .advisor import ADVISOR, pending_until
from .output import BOARD_TAIL

EVENTS = "events.jsonl"
CARD = re.compile(r"^[0-9a-f]{8}-\d+$")
TAIL = 256 * 1024  # bytes read from the end of events.jsonl: a long tool burst still holds a non-system line
__all__ = ["ADVISOR", "Running", "last_activity", "last_output", "running", "turn_over"]


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
    """Return when claude wrote its turn's newest message or tool result line (T2447).

    claude writes `system task_*` lines right after a result, so the walk skips them, other system lines and
    any torn line and reads the line's own `timestamp`; a line without one counts only as the file's last
    line (its mtime), and a trailing partial or thinking_tokens line counts at the mtime (T2469). An advisor
    call still waiting on its answer counts for `ADVISOR` s more (T2448). A line bigger than the tail makes
    the read go further back (T2560).
    """
    return output.newest(run_dir / f"{stem}.stream.jsonl")


def turn_over(run_dir: Path, stem: str | None) -> bool:
    """Return True when the turn has ended: a 'result' line appears after the last OUTPUT line (T2505).

    False when an OUTPUT row comes first, when nothing matches, or the file cannot be read.
    """
    return output.ended(run_dir / f"{stem}.stream.jsonl")


def workers(run_dir: Path) -> float | None:
    """Return until when the card's live free workers count as its work: start plus their timeout (T2451).

    A cheap-tier manager waits on its workers in the background; the free model prints its answer only at
    the end, so the manager's quiet is the worker's time. A worker is live while its pid file names a process.
    A worker's end (its exit file) is activity too: the manager's quiet counts from it (T2468).
    """
    ends: list[float] = []
    for exit_file in [*run_dir.glob(f"worker*.log{EXIT}"), *run_dir.glob(f"children/*/worker*.log{EXIT}")]:
        try:
            ends.append(exit_file.stat().st_mtime)
        except OSError:
            continue
    for pid_file in [*run_dir.glob(f"worker*.log{PID}"), *run_dir.glob(f"children/*/worker*.log{PID}")]:
        try:
            pid = int(pid_file.read_text(encoding="utf-8"))
            if Path(f"/proc/{pid}").exists():
                ends.append(pid_file.stat().st_mtime + freeworker.TIMEOUT)
        except OSError, ValueError:
            continue
    return max(ends, default=None)


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
        stream, start = run_dir / f"{rec.stem}.stream.jsonl", _stem_time(rec.stem)
        own = (
            last_activity(run_dir / EVENTS),
            start,
            last_output(run_dir, rec.stem),
            pending_until(stream),
            workers(run_dir),
            subagent.until(stream, start or 0.0),
        )
        times = [t for t in own if t is not None]
        if times:
            found.append(Running(run_dir.name, run_dir, max(times), rec.pid))
    return found
