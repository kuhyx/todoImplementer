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
from .buildqueue import tickets

PROC = Path("/proc")
CHILDREN = "children"  # an umbrella run keeps its children's run dirs here; each is its own card
SHELLS = frozenset({"bash", "sh", "zsh", "dash"})
START_FIELD = 19  # starttime (stat field 22) in the fields after the `)` that closes the command name
WIDE = 60  # characters of a job's command on the card
EVAL = re.compile(r"eval '((?:[^']|'\\'')*)'")  # claude's Bash tool wraps the command in `eval '...'`
HELD = re.compile(r"(?P<card>\S+) \((?P<cmd>.*)\) since (?P<at>\d{4}-\d\d-\d\d \d\d:\d\d:\d\d)")


def read(path: Path) -> str:
    """Return a /proc file stripped; empty when the process is gone."""
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:  # the process is gone
        return ""


def children(pid: int) -> list[int]:
    """Return the children of every thread of `pid`."""
    found: list[int] = []
    for task in sorted((PROC / str(pid) / "task").glob("*")):
        found.extend(int(part) for part in read(task / "children").split())
    return found


def tree(root: int | None) -> tuple[set[int], list[int]]:
    """Return every process below `root` and the top-most shells among them (the Bash tool's jobs)."""
    below: set[int] = set()
    jobs: list[int] = []
    todo = [] if root is None else [(pid, False) for pid in children(root)]
    while todo:  # a process tree has no cycles
        pid, in_shell = todo.pop()
        below.add(pid)
        shell = read(PROC / str(pid) / "comm") in SHELLS
        if shell and not in_shell:
            jobs.append(pid)
        todo.extend((kid, in_shell or shell) for kid in children(pid))
    return below, jobs


def started(pid: int) -> float | None:
    """Return when the process started (epoch seconds), None when it is gone."""
    stat = read(PROC / str(pid) / "stat")
    boot = next(
        (line.split()[1] for line in read(PROC / "stat").splitlines() if line.startswith("btime")), ""
    )
    fields = stat.rpartition(")")[2].split()
    if len(fields) <= START_FIELD or not boot:
        return None
    return int(boot) + int(fields[START_FIELD]) / os.sysconf("SC_CLK_TCK")


def script(pid: int) -> str:
    """Return the whole of what a process runs, the Bash tool's `eval '...'` wrapper taken off."""
    raw = read(PROC / str(pid) / "cmdline").replace("\0", " ")
    if found := EVAL.search(raw):
        raw = found.group(1).replace("'\\''", "'")
    return raw.strip()


def command(pid: int) -> str:
    """Return the first line of what a shell runs, the Bash tool's wrapper taken off, at most `WIDE` long."""
    raw = script(pid)
    first = raw.splitlines()[0] if raw else ""
    return " ".join(first.split())[:WIDE]


def _key(path: Path) -> str:
    try:
        st = path.stat()
    except OSError:
        return ""
    return f"{os.major(st.st_dev):02x}:{os.minor(st.st_dev):02x}:{st.st_ino}"


def waiters(lock: Path) -> list[int]:
    """Return the pids blocked on `lock` (flock) or on a ticket of its queue (T2164), from `/proc/locks`."""
    keys = {_key(path) for path in (lock, *tickets(lock.parent))} - {""}
    found = []
    for line in read(PROC / "locks").splitlines():
        parts = line.split()
        if "->" in parts and "FLOCK" in parts and len(parts) >= 4 and parts[-3] in keys:  # noqa: PLR2004 - pid key start end
            found.append(int(parts[-4]))
    return found


def mine(pid: int, below: set[int], run_dir: Path) -> bool:
    """Say whether `pid` is the card's: below claude, in its run dir (no child card's) or tagged so."""
    if pid in below:
        return True
    try:
        cwd = str((PROC / str(pid) / "cwd").readlink())
    except OSError:
        cwd = ""
    if cwd == str(run_dir) or cwd.startswith(f"{run_dir}{os.sep}"):
        return not cwd.startswith(f"{run_dir / CHILDREN}{os.sep}")
    return f"{CARD_VAR}={run_dir.name}" in read(PROC / str(pid) / "environ").split("\0")


def _holder(lock: Path) -> tuple[str, float | None]:
    """Return who holds the lock (its card, or its command for a card-less build) and since when."""
    found = HELD.fullmatch(read(lock.with_name(HOLDER)))
    if found is None:
        return "?", None
    who = found["card"] if found["card"] != "?" else found["cmd"]
    return who, time.mktime(time.strptime(found["at"], "%Y-%m-%d %H:%M:%S"))


holder = _holder  # the board's own checks name the holder they queue behind the same way (T2185)


def scan(claude_pid: int | None, run_dir: Path, lock: Path) -> dict[str, Any] | None:
    """Return what the turn's live background job waits on (None: no job): `{lock, who, since}`."""
    below, jobs = tree(claude_pid)
    if not jobs:
        return None
    for pid in waiters(lock):
        if mine(pid, below, run_dir):
            who, since = _holder(lock)
            return {"lock": True, "who": who, "since": since if since is not None else started(pid)}
    job = min(jobs, key=lambda pid: started(pid) or 0.0)
    return {"lock": False, "who": command(job), "since": started(job)}
