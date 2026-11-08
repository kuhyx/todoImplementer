"""The turn a run has in flight: `turn.pid` in the run dir, and the processes behind it.

A turn runs under its own host (`turnhost`, a systemd unit in production) and outlives the server. The record
names it: `stem` + `role` identify the turn's files, `unit` the systemd unit (None: a direct launch), `pid`
and `start` claude (its pid is its process group), `host_pid`/`host_start` the host. Pid reuse is ruled out
by the start time. A record with no `stem` is a pipe-spawned turn of the old server: it can only be reaped,
and only a recorded turn is, so kuhy's own `claude --resume` session in the worktree is never touched.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .files import read_json, write_json

PROC = Path("/proc")
POLL = 0.05
RECORD = "turn.pid"
START_FIELD = 19  # starttime (stat field 22) in the fields after the `)` that closes the command name


@dataclass(frozen=True)
class Record:
    """What `turn.pid` holds; every field is optional so that an older or half-written record still reads."""

    stem: str | None = None
    role: str | None = None
    unit: str | None = None
    pid: int | None = None
    start: str | None = None
    host_pid: int | None = None
    host_start: str | None = None
    launched: float = 0.0


def _stat(pid: int) -> list[str] | None:
    """Return the stat fields after the command name (state first), or None when the process is gone."""
    try:
        text = (PROC / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return text.rpartition(")")[2].split()


def start_of(pid: int) -> str | None:
    """Return the process start time (clock ticks since boot, as text), None when it is gone."""
    fields = _stat(pid)
    return fields[START_FIELD] if fields else None


def matches(pid: int | None, start: str | None) -> bool:
    """Say whether that very process (same start time) still has a process-table entry, zombie or not."""
    return pid is not None and start is not None and start_of(pid) == start


def alive(pid: int | None, start: str | None) -> bool:
    """Return `matches` and not a zombie: a zombie is dead, its parent has yet to reap it."""
    fields = _stat(pid) if matches(pid, start) and pid is not None else None
    return fields is not None and fields[0] != "Z"


def read(run_dir: Path) -> Record | None:
    """Return the run's turn record, None when there is none or it is unreadable."""
    data = read_json(run_dir / RECORD)
    if not isinstance(data, dict):
        return None
    return Record(**{k: v for k, v in data.items() if k in Record.__dataclass_fields__})


def write(run_dir: Path, **fields: Any) -> None:  # noqa: ANN401 - the record's own field types
    """Merge fields into the record (creating it); atomic, so a reader never sees half a record."""
    write_json(run_dir / RECORD, {**asdict(read(run_dir) or Record()), **fields})


def begin(run_dir: Path, stem: str, role: str, unit: str | None) -> Record:
    """Start a fresh record for a turn about to be launched; the host fills in the pids."""
    rec = Record(stem=stem, role=role, unit=unit, launched=time.time())
    write_json(run_dir / RECORD, asdict(rec))
    return rec


def record(run_dir: Path, pid: int) -> None:
    """Note a pipe-spawned turn the old way (pid and start only): such a record can only be reaped."""
    start = start_of(pid)
    if start is not None:
        write_json(run_dir / RECORD, asdict(Record(pid=pid, start=start)))


def clear(run_dir: Path) -> None:
    """Forget the record once the turn was consumed."""
    (run_dir / RECORD).unlink(missing_ok=True)


def terminate(pid: int | None, start: str | None, grace: float = 3.0) -> bool:
    """SIGTERM, wait `grace`, then SIGKILL that process group, if it is the recorded process.

    The group always gets the SIGKILL, so grandchildren of a leader that obeyed SIGTERM die too.
    Return whether there was anything to signal.
    """
    if pid is None or not matches(pid, start):
        return False
    for sig in (signal.SIGTERM, signal.SIGKILL):
        with contextlib.suppress(ProcessLookupError):
            os.killpg(pid, sig)
        deadline = time.monotonic() + (grace if sig == signal.SIGTERM else 0.0)
        while time.monotonic() < deadline and alive(pid, start):
            time.sleep(POLL)
    return True


def reap(run_dir: Path, grace: float = 3.0) -> int | None:
    """Kill the recorded turn's process group and forget the record; return its pid, None if nothing ran.

    Only for a record without a `stem`: the old server's turn, whose reader is gone. The resumed session
    would otherwise edit the same worktree in parallel with it.
    """
    rec = read(run_dir)
    found = rec.pid if rec is not None and terminate(rec.pid, rec.start, grace) else None
    clear(run_dir)
    return found
