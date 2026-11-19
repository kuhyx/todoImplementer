"""Spot a turn that is done but not exited: its result is in, its stream is silent, and no shell is running.

`claude -p` that ended its reply with `R:` while a background Bash task ran stays alive for the task's
notice. If the task finished without a notice reaching it, the process idles for hours, its unit stays
active and kuhy's queued `send` is never read. A shell child (the Bash tool runs `bash -c`) means a build
is still going: wait. MCP servers are children too, so only shells count.

A turn is idle once its stream is silent for the limit and no shell was seen below claude for `SHELL_GRACE`
(T2194). Without the grace, a job that outlived the limit had claude stopped the instant its shell left,
before claude could take the job's notice and go on (it takes one 0.1 s, at most 5.5 s, over 237 notices).
"""

from __future__ import annotations

import math
from pathlib import Path

SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
PROC = Path("/proc")
LOOK_EVERY = 1.0  # seconds between two looks for a shell below an idle claude (a few small /proc reads)
SHELL_GRACE = 60.0  # seconds a turn gets after its last shell left to take the job's notice


def _read(path: Path) -> str:
    try:
        return path.read_text().strip()
    except OSError:  # the process is gone
        return ""


def _children(pid: int) -> list[int]:
    """Children of every thread of `pid` (the kernel lists a child under the thread that spawned it)."""
    found: list[int] = []
    for task in sorted((PROC / str(pid) / "task").glob("*")):
        found.extend(int(part) for part in _read(task / "children").split())
    return found


def shell_running(root: int | None) -> bool:
    """Return whether a shell is anywhere below process `root` (None: unknown, so nothing is running)."""
    todo = [] if root is None else _children(root)
    while todo:  # a process tree has no cycles
        pid = todo.pop()
        if _read(PROC / str(pid) / "comm") in SHELLS:
            return True
        todo.extend(_children(pid))
    return False


class Clock:
    """When the turn's stream last spoke (`heard`) and when a shell was last seen below claude."""

    def __init__(self, now: float) -> None:  # noqa: D107
        self.heard_at = now
        self.shell_at = -math.inf  # no shell seen yet: no grace to give
        self.looked = now - LOOK_EVERY

    def heard(self, now: float) -> None:
        """Note that the stream spoke at `now`."""
        self.heard_at = now

    def _quiet(self, now: float, limit: float) -> bool:
        return now - self.heard_at >= limit and now - self.shell_at >= SHELL_GRACE

    def due(self, *, finished: bool, now: float, limit: float, claude_pid: int | None) -> bool:
        """Say whether a turn that reported its result is idle (see the module) and is to be ended.

        A shell is looked for every `LOOK_EVERY` s, and once more before saying yes.
        """
        if not finished:
            return False
        if now - self.looked >= LOOK_EVERY or self._quiet(now, limit):
            self.looked = now
            if shell_running(claude_pid):
                self.shell_at = now
        return self._quiet(now, limit)
