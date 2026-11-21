"""Name why a running card went quiet: memory, the build lock, a job, or the model (T2402).

The cause is the ticket's signature, so the same cause is one ticket however often it comes back. Memory
comes first: under memory pressure every other wait is a symptom (2026-11-20: the build lock, pnpm, ssh and
claude itself all sat in `mem_cgroup_handle_over_high` behind one card's 16 GB render). `CGROUP` and
`bgwait.PROC` are the tests' seams.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from todoimpl.runner import bgwait, buildlock, cardslice

from . import program
from .scan import Running

CGROUP = Path(f"/sys/fs/cgroup/user.slice/user-{os.getuid()}.slice/user@{os.getuid()}.service")
PRESSURE = 10.0  # % of the last 10 s in which every task of the slice waited on memory
FULL = re.compile(r"^full avg10=(?P<avg>[\d.]+)", re.MULTILINE)
GIB = 1 << 30
GRACE = 1.0  # s: a process start time is read in whole seconds of boot time plus clock ticks


def pressure(group: Path) -> float:
    """Return the cgroup's `full avg10` memory pressure, 0 when it cannot be read."""
    found = FULL.search(bgwait.read(group / "memory.pressure"))
    return float(found["avg"]) if found else 0.0


def biggest(group: Path) -> tuple[str, int] | None:
    """Return the unit below `group` (a service or scope) that holds the most memory, and how much."""
    sizes: list[tuple[str, int]] = []
    for unit in group.rglob("*"):
        if unit.suffix not in (".service", ".scope") or not unit.is_dir():
            continue
        try:
            sizes.append((unit.name, int(bgwait.read(unit / "memory.current"))))
        except ValueError:
            continue
    return max(sizes, key=lambda pair: pair[1], default=None)


def diagnose(run: Running) -> tuple[str, str]:
    """Return the stall's signature and a one-line detail."""
    parent = CGROUP / cardslice.PARENT
    for group in (parent / cardslice.card_slice(run.card), parent):
        if (full := pressure(group)) >= PRESSURE:
            top = biggest(parent)
            hog = f"; biggest unit {top[0]} {top[1] / GIB:.1f} GiB" if top else ""
            return "stall-memory", f"{group.name} memory pressure full avg10={full:.0f}%{hog}"
    wait = bgwait.scan(run.pid, run.run_dir, buildlock.root() / buildlock.LOCK)
    young = bgwait.newest(run.pid)
    if wait is None or (not wait["lock"] and young is not None and young < run.since - GRACE):
        # T2449: every job is older than the last activity, so its (capped) result already reached the model
        return "stall-model", "no command runs: waiting on the model"
    if wait["lock"]:
        return "stall-buildlock", f"waits on the build lock held by {wait['who']}"
    pid = bgwait.job(run.pid)  # the signature reads the whole script, the card only its first 60 chars
    whole = bgwait.script(pid) if pid is not None else ""
    return f"stall-job-{program.name(whole or str(wait['who']))}", f"waits on: {wait['who']}"
