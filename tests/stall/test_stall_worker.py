"""A live free worker is the card's work: its manager waits on it, so the manager's quiet is no stall (T2451).

2026-11-21: cheap-tier managers ran `freeworker wait worker-3.log` in the background and ended their turn; the
free model worked for 6-9 min and printed its answer only at the end, so each wait was a `stall-job-python`.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from todoimpl.runner import freeworker, orphans
from todoimpl.stall import scan

STEM = "manager-1000.000"


def _card(tmp_path: Path) -> Path:
    run_dir = tmp_path / "eeeeeeee-0"
    (run_dir / "children" / "eeeeeeee-3").mkdir(parents=True)
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    return run_dir


def _pid_file(path: Path, pid: object, at: float) -> None:
    path.write_text(str(pid), "utf-8")
    os.utime(path, (at, at))


def test_t2451_a_live_worker_counts_as_work_until_its_timeout(tmp_path: Path) -> None:
    run_dir = _card(tmp_path)
    _pid_file(run_dir / "children" / "eeeeeeee-3" / "worker-3.log.pid", os.getpid(), 5000.0)
    assert [r.since for r in scan.running(tmp_path)] == [5000.0 + freeworker.TIMEOUT]


def test_t2451_a_dead_or_unreadable_worker_does_not(tmp_path: Path) -> None:
    run_dir = _card(tmp_path)
    gone = subprocess.Popen(["true"])  # a pid that is surely over
    gone.wait()
    _pid_file(run_dir / "worker-1.log.pid", gone.pid, 5000.0)
    _pid_file(run_dir / "worker-2.log.pid", "x", 6000.0)
    assert [r.since for r in scan.running(tmp_path)] == [1000.0]


def test_t2468_a_worker_that_just_ended_counts_as_work_at_its_end(tmp_path: Path) -> None:
    # 2026-11-21 f2199a40-0: the worker ran 22 min; it exited, its pid file went, and the watch filed the
    # manager's 254 s of quiet 2 s later, though the manager answered 7 s after the worker's end
    run_dir = _card(tmp_path)
    _pid_file(run_dir / "children" / "eeeeeeee-3" / "worker-3.log.exit", 0, 7000.0)
    _pid_file(run_dir / "worker-1.log.exit", 0, 6000.0)
    (run_dir / "worker-2.log.exit").symlink_to(run_dir / "gone")  # removed between the listing and the stat
    assert [r.since for r in scan.running(tmp_path)] == [7000.0]
