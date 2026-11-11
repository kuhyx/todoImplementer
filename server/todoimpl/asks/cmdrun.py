"""Run an allow-listed command as kuhy's user in the task worktree: 60 s cap, last 50 lines plus exit code."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from pathlib import Path
from typing import Any

CAP = 60.0
TAIL_LINES = 50
TIMED_OUT = 124


def run(command: str, cwd: Path | None, cap: float = CAP) -> dict[str, Any]:
    """Return {exit, tail, capped}; a command over `cap` seconds is killed and reports exit 124."""
    where = cwd if cwd is not None and cwd.is_dir() else Path.home()
    proc = subprocess.Popen(  # noqa: S603 - an exact string kuhy allow-listed or clicked on the card
        ["bash", "-c", command],  # noqa: S607
        cwd=where,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    capped = False
    try:
        out, _ = proc.communicate(timeout=cap)
    except subprocess.TimeoutExpired:
        capped = True
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        out, _ = proc.communicate()
    code = TIMED_OUT if capped else proc.returncode
    tail = "\n".join((out or "").splitlines()[-TAIL_LINES:])
    return {"exit": code, "tail": tail, "capped": capped}
