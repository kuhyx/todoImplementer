"""Which cards run now, and since when each one has shown no real activity (T2402).

A card runs while its turn's claude is alive (`turn.pid`). Real activity is the card's own `activity` events
(tool calls, text, results) in `events.jsonl`, and the newest tool result or assistant message
line of the turn's stream file (thinking included, T2418), at that line's own time (T2447); the
board's `system` lines, claude's other stream lines or a touched file are not, so nothing can look alive by
pinging. An advisor call waiting on its answer, on any thread, is work for a while (T2448, T2486).
A fresh turn counts from its start (the time in its stem),
not from the last cycle's events.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from todoimpl.runner import freeworker, orphans
from todoimpl.runner.workerwait import EXIT, PID

from .advisor import ADVISOR, pending_until
from .advisor import stamp as _stamp

EVENTS = "events.jsonl"
CARD = re.compile(r"^[0-9a-f]{8}-\d+$")
TAIL = 256 * 1024  # bytes read from the end of events.jsonl: a long tool burst still holds a non-system line
PARTIAL = "stream_event"  # a chunk of the message the model writes now (`--include-partial-messages`)
THINKING = "thinking_tokens"  # claude's estimate of the thinking so far, written while the model thinks
OUTPUT = frozenset({"assistant", "user"})  # stream lines that are real work: a message, or a tool's result
BOARD_TAIL = 64 * 1024  # the board polls every running card, so it reads less than the watch does
__all__ = ["ADVISOR", "Running", "last_activity", "last_output", "running"]


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


def _pending_advisor(row: dict[str, object]) -> bool:
    """Tell whether a message line ends on a server tool call (the advisor) whose answer has not come."""
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    last = content[-1] if isinstance(content, list) and content else None
    return isinstance(last, dict) and last.get("type") == "server_tool_use"


def _writing(row: object) -> bool:
    """Tell whether a stream line is one claude writes only while the model streams (T2452, T2469).

    While the model thinks, claude interleaves `system thinking_tokens` lines with the `thinking_delta`
    events, so the last line is often such a system line.
    """
    if not isinstance(row, dict):
        return False
    return row.get("type") == PARTIAL or (row.get("type") == "system" and row.get("subtype") == THINKING)


def last_output(run_dir: Path, stem: str | None) -> float | None:
    """Return when claude wrote its turn's newest message or tool result line (T2447).

    claude writes `system task_*` lines right after a result, so the walk skips them, other system lines and
    any torn line and reads the line's own `timestamp`; a line without one counts only as the file's last
    line (its mtime), and a trailing partial or thinking_tokens line counts at the mtime (T2469). An advisor
    call still waiting on its answer counts for `ADVISOR` s more (T2448).
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
            if back == 0 and _writing(row):
                return mtime  # the model is writing its answer or thinking right now (T2452, T2469)
            continue
        at = _stamp(row)
        if at is None:
            return mtime if back == 0 else None
        return at + ADVISOR if _pending_advisor(row) else at
    return None


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
        own = (
            last_activity(run_dir / EVENTS),
            _stem_time(rec.stem),
            last_output(run_dir, rec.stem),
            pending_until(run_dir / f"{rec.stem}.stream.jsonl"),
            workers(run_dir),
        )
        times = [t for t in own if t is not None]
        if times:
            found.append(Running(run_dir.name, run_dir, max(times), rec.pid))
    return found
