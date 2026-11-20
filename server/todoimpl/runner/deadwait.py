"""Judge what a silent turn waits on: healthy, dead or unknown, from a few /proc reads (T2195-T2197).

A job is a shell below claude (with all its processes) or one of the card's transient units in claude's slice
(a `systemd-run` job is no child of claude; `bgwait.mine` tells the card's). A job is healthy when it holds a
place in the build lock's queue, one of its processes does real work (CPU, not a shell, sleep or poll tool),
or it is an event wait (`gh run watch`, `systemd-run --wait`, `inotifywait`, a blocking `flock`). It is dead
when (a) its `pgrep -f <pattern>` matches nothing but itself and its ancestors (the pattern sits in the
loop's own command line, kartka 22 min); (b) its processes used no CPU for `STILL` s, every one asleep in a
pipe read, a futex or a wait for a child (a background job inside `$(...)` held the pipe, b11.sh 21 min);
(c) it names another card that is done, or whose turn is gone and that is not shipping. Else unknown.
Only a dead job is ever stopped (`stop`), and only processes that are still the ones judged.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import bgwait, deadrules

if TYPE_CHECKING:
    from collections.abc import Callable

HEALTHY, DEAD, UNKNOWN = "healthy", "dead", "unknown"
STILL = 120.0  # no CPU this long, all asleep in a pipe, futex or wait: a deadlock
CGROUP = Path("/sys/fs/cgroup")
TURN_UNIT = "todoimpl-turn-"
IDLE = ("pipe_read", "pipe_wait", "futex", "do_wait", "sigsuspend")
LAZY = frozenset({*bgwait.SHELLS, "sleep", "pgrep", "pidof", "ps", "systemctl", "flock", "timeout", "tail"})
EVENT = re.compile(
    r"^(?:\S*/)?(?:gh run watch|inotifywait|systemd-run .*--wait|flock (?!.*(?:-n|--nonblock)\b))"
)
KILL: Callable[[int, int], None] = os.kill
STOP_UNIT: Callable[[str], object] = lambda unit: subprocess.run(  # noqa: E731, S603 - a unit name we found
    ["systemctl", "--user", "stop", unit],  # noqa: S607 - the user manager's own tool
    check=False,
    capture_output=True,
    timeout=30,
)


@dataclass(frozen=True)
class Job:
    """One wait: its top process, every process in it with their start times, its unit when it is one."""

    top: int
    pids: tuple[int, ...]
    starts: tuple[float | None, ...]
    unit: str | None = None


@dataclass(frozen=True)
class Verdict:
    """`verdict` (healthy, dead, unknown), the rule that decided it, the job's command and the job."""

    verdict: str
    rule: str
    who: str
    job: Job | None = None
    detail: str = ""  # the pgrep pattern or the other card


def _job(pids: list[int], unit: str | None = None) -> Job:
    return Job(pids[0], tuple(pids), tuple(bgwait.started(p) for p in pids), unit)


def _units(claude: int, run_dir: Path, below: set[int]) -> list[Job]:
    """Return the card's transient units beside its turn unit in claude's slice."""
    path = bgwait.read(bgwait.PROC / str(claude) / "cgroup").rpartition("::")[2].strip("/")
    if not path:
        return []
    jobs = []
    for unit in sorted((CGROUP / path).parent.glob("*.s*")):
        pids = [int(p) for p in bgwait.read(unit / "cgroup.procs").split()]
        if not unit.name.startswith(TURN_UNIT) and pids and any(bgwait.mine(p, below, run_dir) for p in pids):
            # capped.sh moves heavy tools into their own scope: count every process below too (T2390)
            jobs.append(_job(list(dict.fromkeys(k for p in pids for k in deadrules.subtree(p))), unit.name))
    return jobs


class Judge:
    """Judge a card's jobs on each `look`; keeps CPU samples between looks (the clock is the tests' seam)."""

    def __init__(self, run_dir: Path, lock: Path, clock: Callable[[], float] = time.monotonic) -> None:
        """Judge the jobs of the card in `run_dir`; `lock` is the build lock whose queue counts as healthy."""
        self.run_dir, self.lock, self.clock = run_dir, lock, clock
        self.cpu: dict[tuple[int, float | None], int] = {}
        self.still: dict[Job, tuple[int, float]] = {}

    def look(self, claude: int | None) -> list[Verdict]:
        """Return one verdict per live job of the turn whose claude is `claude`."""
        below, tops = bgwait.tree(claude)
        jobs = [_job(deadrules.subtree(top)) for top in tops]
        jobs += _units(claude, self.run_dir, below) if claude is not None else []
        queued = set(bgwait.waiters(self.lock))
        cpu = {
            (p, s): deadrules.ticks(p, deadrules.UTIME + 1)
            for job in jobs
            for p, s in zip(job.pids, job.starts, strict=True)
        }
        found = [self._judge(job, queued, cpu) for job in jobs]
        self.cpu = cpu
        self.still = {job: self.still[job] for job in jobs if job in self.still}
        return found

    def _working(self, job: Job, cpu: dict[tuple[int, float | None], int]) -> bool:
        keys = zip(job.pids, job.starts, strict=True)
        lazy = {pid for pid in job.pids if bgwait.read(bgwait.PROC / str(pid) / "comm") in LAZY}
        return any(k[0] not in lazy and k in self.cpu and cpu[k] > self.cpu[k] for k in keys)

    def _deadlocked(self, job: Job) -> bool:
        now, ticks = self.clock(), sum(deadrules.ticks(pid) for pid in job.pids)
        seen, since = self.still.get(job, (ticks, now))
        self.still[job] = (ticks, since if seen == ticks else now)
        idle = all(any(w in found for w in IDLE) for p in job.pids for found in deadrules.wchans(p))
        return idle and seen == ticks and now - since >= STILL

    def _healthy(self, job: Job, queued: set[int], cpu: dict[tuple[int, float | None], int]) -> str:
        if queued & set(job.pids):
            return "lock-queue"
        if self._working(job, cpu):
            return "working"
        return "event-wait" if any(EVENT.search(deadrules.cmdline(p)) for p in job.pids[1:]) else ""

    def _dead(self, job: Job, script: str) -> tuple[str, str] | None:
        if all(bgwait.read(bgwait.PROC / str(pid) / "comm") in LAZY for pid in job.pids):  # a poll loop now
            pattern = deadrules.pgrep_pattern(script)
            if pattern is not None and deadrules.self_only(pattern, job.top, job.pids):
                return "pgrep-self", pattern
            if other := deadrules.gone_card(script, self.run_dir):
                return "cross-card", other
        return ("deadlock", "") if self._deadlocked(job) else None

    def _judge(self, job: Job, queued: set[int], cpu: dict[tuple[int, float | None], int]) -> Verdict:
        who = bgwait.command(job.top)
        if rule := self._healthy(job, queued, cpu):
            return Verdict(HEALTHY, rule, who, job)
        if dead := self._dead(job, bgwait.script(job.top)):
            return Verdict(DEAD, dead[0], who, job, dead[1])
        return Verdict(UNKNOWN, "", who, job)


def overall(verdicts: list[Verdict]) -> Verdict:
    """Return the card's verdict: a dead job first, then a healthy one, else unknown."""
    for want in (DEAD, HEALTHY):
        if found := next((v for v in verdicts if v.verdict == want), None):
            return found
    return verdicts[0] if verdicts else Verdict(UNKNOWN, "", "")


def _tell(pid: int, note: str) -> None:
    """Write `note` to the job's stderr (the Bash tool's output), so the turn reads why its job ended."""
    try:
        fd = os.open(bgwait.PROC / str(pid) / "fd" / "2", os.O_WRONLY | os.O_APPEND | os.O_NONBLOCK)
    except OSError:
        return
    try:
        os.write(fd, note.encode())
    except OSError:  # a full pipe: the inbox note still carries it
        pass
    finally:
        os.close(fd)


def stop(verdict: Verdict, note: str) -> None:
    """Stop a dead job: its unit, else every process in it that is still the one judged (no reused pid)."""
    job = verdict.job
    if job is None:
        return
    _tell(job.top, note)
    if job.unit is not None:
        STOP_UNIT(job.unit)
        return
    for pid, start in zip(job.pids, job.starts, strict=True):
        if bgwait.started(pid) == start:
            KILL(pid, signal.SIGTERM)
