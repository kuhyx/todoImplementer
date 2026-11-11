"""Spot a turn that is done but not exited: its result is in, its stream is silent, and no shell is running.

`claude -p` that ended its reply with `R:` while a background Bash task ran stays alive for the task's
notice. If the task finished without a notice reaching it, the process idles for hours, its unit stays
active and kuhy's queued `send` is never read. A shell child (the Bash tool runs `bash -c`) means a build
is still going: wait. MCP servers are children too, so only shells count.
"""

from __future__ import annotations

from pathlib import Path

SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
PROC = Path("/proc")


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


def should_stop(*, finished: bool, silent_for: float, limit: float, claude_pid: int | None) -> bool:
    """Say whether a turn that reported its result and went silent for `limit` seconds is to be ended."""
    return finished and silent_for >= limit and not shell_running(claude_pid)
