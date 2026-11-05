"""Claude turns an earlier server instance left running (KillMode=process: they outlive a restart).

Each turn's pid and start time are recorded in the run dir while it runs. Only a recorded turn is reaped, so
kuhy's own `claude --resume` session or editor in the same worktree is never touched.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import time
from pathlib import Path

PROC = Path("/proc")
POLL = 0.05
RECORD = "turn.pid"
START_FIELD = 19  # starttime (stat field 22) in the fields after the `)` that closes the command name


def _stat(pid: int) -> list[str] | None:
    """Return the stat fields after the command name (state first), or None when the process is gone."""
    try:
        text = (PROC / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    return text.rpartition(")")[2].split()


def _start(pid: int) -> str | None:
    fields = _stat(pid)
    return fields[START_FIELD] if fields else None


def record(run_dir: Path, pid: int) -> None:
    """Note the live turn's pid (also its pgid: `claude.spawn` starts a new session) and start time."""
    start = _start(pid)
    if start is not None:
        (run_dir / RECORD).write_text(json.dumps({"pid": pid, "start": start}), encoding="utf-8")


def clear(run_dir: Path) -> None:
    """Forget the record once the turn ended."""
    (run_dir / RECORD).unlink(missing_ok=True)


def _recorded(run_dir: Path) -> int | None:
    """Return the recorded pid if that very process (same start time) still exists."""
    try:
        data = json.loads((run_dir / RECORD).read_text(encoding="utf-8"))
        pid, start = int(data["pid"]), str(data["start"])
    except OSError, ValueError, KeyError, TypeError:
        return None
    return pid if _start(pid) == start else None


def _alive(pid: int) -> bool:
    fields = _stat(pid)
    return fields is not None and fields[0] != "Z"  # a zombie is dead; its parent has yet to reap it


def reap(run_dir: Path, grace: float = 3.0) -> int | None:
    """SIGTERM then SIGKILL the recorded turn's process group; return its pid, None if nothing to kill.

    The resumed session would otherwise edit the same worktree in parallel with the orphan.
    """
    pid = _recorded(run_dir)
    if pid is not None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(pid, sig)
            deadline = time.monotonic() + (grace if sig == signal.SIGTERM else 0.0)
            while time.monotonic() < deadline and _alive(pid):
                time.sleep(POLL)
    clear(run_dir)
    return pid
