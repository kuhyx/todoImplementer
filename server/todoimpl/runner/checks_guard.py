"""One check run per run dir: a new run first stops the run a previous server left behind (T1889).

Checks are the server's own children, each in its own process group so a timeout can kill the whole tree.
The board unit stops with KillMode=process, so a restart leaves a running check alive while the new server
runs the checks again in the same worktree; two `make test` runs there delete each other's coverage files
(`cov-clean`, `coverage combine`) and the survivor reports 49 % coverage. Nobody reads the old run's result
any more, so the new run stops it. `<run dir>/checks.pgid` holds the group id and its leader's start time;
the start time keeps a reused pid from being killed.
"""

from __future__ import annotations

import contextlib
import os
import signal
import time
from pathlib import Path

RECORD = "checks.pgid"


def proc_stat(pid: int) -> tuple[str, str] | None:
    """Return (state, start time in clock ticks) of the process, or None when it is gone."""
    try:
        stat = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8")
    except OSError:
        return None
    fields = stat.rsplit(")", 1)[1].split()  # comm may hold spaces; fields from 3 on follow the last ')'
    return fields[0], fields[19]  # state is field 3, starttime field 22


def remember(run_dir: Path, pid: int) -> None:
    """Record the group a check just started; a pid that is already gone needs no record."""
    if (stat := proc_stat(pid)) is not None:
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / RECORD).write_text(f"{pid} {stat[1]}\n", encoding="utf-8")


def forget(run_dir: Path, pid: int) -> None:
    """Drop the record once the check is over, unless a newer run already replaced it."""
    record = run_dir / RECORD
    with contextlib.suppress(OSError):
        if record.read_text(encoding="utf-8").split()[:1] == [str(pid)]:
            record.unlink()


def stop_stale(run_dir: Path, grace: float = 3.0) -> None:
    """Stop the recorded check group if its leader still is the process that was recorded."""
    record = run_dir / RECORD
    try:
        pgid_text, started = record.read_text(encoding="utf-8").split()
        pgid = int(pgid_text)
    except OSError, ValueError:
        record.unlink(missing_ok=True)
        return
    if (stat := proc_stat(pgid)) is not None and stat[1] == started:
        _stop_group(pgid, grace)
    record.unlink(missing_ok=True)


def _stop_group(pgid: int, grace: float) -> None:
    """SIGTERM the group, wait up to `grace` seconds for its leader to exit, then SIGKILL what is left."""
    _signal(pgid, signal.SIGTERM)
    deadline = time.monotonic() + grace
    while _running(pgid) and time.monotonic() < deadline:
        time.sleep(0.05)
    _signal(pgid, signal.SIGKILL)


def _running(pid: int) -> bool:
    stat = proc_stat(pid)
    return stat is not None and stat[0] != "Z"


def _signal(pgid: int, sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError, PermissionError):
        os.killpg(pgid, sig)
