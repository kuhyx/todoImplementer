"""Name what an idle turn waits on: the build lock (and who holds it) or a background job (T2124).

A turn whose reply ended (`R:`) while a background Bash job runs looked like plain "working" for half an hour:
its job waited on the machine-wide build lock. The lock waiter is often no child of claude (`scripts/bg.sh`
runs the job in a `systemd-run` unit), so a waiter counts as this card's when it is below claude, runs in the
card's run dir (its worktree) or carries the card in `TODOIMPL_BUILD_CARD`. Blocked flock requests are the
`->` lines of `/proc/locks`. Everything here is a handful of small /proc reads; `PROC` is the tests' seam.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any

from .buildlock import CARD_VAR, HOLDER

PROC = Path("/proc")
CHILDREN = "children"  # an umbrella run keeps its children's run dirs here; each is its own card
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
START_FIELD = 19  # starttime (stat field 22) in the fields after the `)` that closes the command name
WIDE = 60  # characters of a job's command on the card
EVAL = re.compile(r"eval '((?:[^']|'\\'')*)'")  # claude's Bash tool wraps the command in `eval '...'`
HELD = re.compile(r"(?P<card>\S+) \((?P<cmd>.*)\) since (?P<at>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:  # the process is gone
        return ""


def _children(pid: int) -> list[int]:
    found: list[int] = []
    for task in sorted((PROC / str(pid) / "task").glob("*")):
        found.extend(int(part) for part in _read(task / "children").split())
    return found


def _tree(root: int | None) -> tuple[set[int], list[int]]:
    """Return every process below `root` and the top-most shells among them (the Bash tool's jobs)."""
    below: set[int] = set()
    jobs: list[int] = []
    todo = [] if root is None else [(pid, False) for pid in _children(root)]
    while todo:  # a process tree has no cycles
        pid, in_shell = todo.pop()
        below.add(pid)
        shell = _read(PROC / str(pid) / "comm") in SHELLS
        if shell and not in_shell:
            jobs.append(pid)
        todo.extend((kid, in_shell or shell) for kid in _children(pid))
    return below, jobs


def started(pid: int) -> float | None:
    """Return when the process started (epoch seconds), None when it is gone."""
    stat = _read(PROC / str(pid) / "stat")
    boot = next(
        (line.split()[1] for line in _read(PROC / "stat").splitlines() if line.startswith("btime")), ""
    )
    fields = stat.rpartition(")")[2].split()
    if len(fields) <= START_FIELD or not boot:
        return None
    return int(boot) + int(fields[START_FIELD]) / os.sysconf("SC_CLK_TCK")


def command(pid: int) -> str:
    """Return the first line of what a shell runs, the Bash tool's wrapper taken off, at most `WIDE` long."""
    raw = _read(PROC / str(pid) / "cmdline").replace("\0", " ")
    if found := EVAL.search(raw):
        raw = found.group(1).replace("'\\''", "'")
    first = raw.strip().splitlines()[0] if raw.strip() else ""
    return " ".join(first.split())[:WIDE]


def waiters(lock: Path) -> list[int]:
    """Return the pids blocked on `lock` (flock), from `/proc/locks`."""
    try:
        st = lock.stat()
    except OSError:
        return []
    key = f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"
    found = []
    for line in _read(PROC / "locks").splitlines():
        parts = line.split()
        if "->" in parts and "FLOCK" in parts and len(parts) >= 4 and parts[-3] == key:  # noqa: PLR2004 - pid key start end
            found.append(int(parts[-4]))
    return found


def _mine(pid: int, below: set[int], run_dir: Path) -> bool:
    if pid in below:
        return True
    try:
        cwd = str((PROC / str(pid) / "cwd").readlink())
    except OSError:
        cwd = ""
    if cwd == str(run_dir) or cwd.startswith(f"{run_dir}{os.sep}"):
        return not cwd.startswith(f"{run_dir / CHILDREN}{os.sep}")
    return f"{CARD_VAR}={run_dir.name}" in _read(PROC / str(pid) / "environ").split("\0")


def _holder(lock: Path) -> tuple[str, float | None]:
    """Return who holds the lock (its card, or its command for a card-less build) and since when."""
    found = HELD.fullmatch(_read(lock.with_name(HOLDER)))
    if found is None:
        return "?", None
    who = found["card"] if found["card"] != "?" else found["cmd"]
    return who, time.mktime(time.strptime(found["at"], "%Y-%m-%d %H:%M:%S"))


def scan(claude_pid: int | None, run_dir: Path, lock: Path) -> dict[str, Any] | None:
    """Return what the turn's live background job waits on (None: no job): `{lock, who, since}`."""
    below, jobs = _tree(claude_pid)
    if not jobs:
        return None
    for pid in waiters(lock):
        if _mine(pid, below, run_dir):
            who, since = _holder(lock)
            return {"lock": True, "who": who, "since": since if since is not None else started(pid)}
    job = min(jobs, key=lambda pid: started(pid) or 0.0)
    return {"lock": False, "who": command(job), "since": started(job)}
