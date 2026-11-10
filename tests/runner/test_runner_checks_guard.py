"""One check run per run dir: a restarted server stops the checks its predecessor left running (T1889)."""

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest
from runnerfakes import Env
from schedfakes import wait
from todoimpl.runner import checks, checks_guard


def _alive(pid: int) -> bool:
    state = checks_guard.proc_stat(pid)
    return state is not None and state[0] != "Z"


def test_t1889_a_new_check_run_stops_the_one_a_dead_server_left_running(world: Env, tmp_path: Path) -> None:
    # The old server's check: still running in the worktree after its server died (KillMode=process).
    run_dir = tmp_path / "run"
    old: list[checks.CheckResult] = []

    def old_server() -> None:
        old.append(checks.run_check("tests", "sleep 30", tmp_path, run_dir, 60))

    thread = threading.Thread(target=old_server, daemon=True)
    thread.start()
    wait((run_dir / checks_guard.RECORD).exists)
    pgid = int((run_dir / checks_guard.RECORD).read_text().split()[0])
    assert _alive(pgid)
    # The restarted server runs the checks again: the leftover run must be gone before the new one starts.
    new = checks.run_check("tests", "true", tmp_path, run_dir, 10)
    thread.join(5)
    assert new.passed
    assert not _alive(pgid)
    assert old
    assert not old[0].passed
    assert not (run_dir / checks_guard.RECORD).exists()


def _leader(*argv: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(argv, start_new_session=True)


def test_a_record_whose_start_time_differs_is_a_reused_pid_and_is_left_alone(tmp_path: Path) -> None:
    proc = _leader("sleep", "30")
    try:
        (tmp_path / checks_guard.RECORD).write_text(f"{proc.pid} 1\n", encoding="utf-8")
        checks_guard.stop_stale(tmp_path)
        assert proc.poll() is None
        assert not (tmp_path / checks_guard.RECORD).exists()
    finally:
        proc.kill()
        proc.wait()


@pytest.mark.parametrize("text", [None, "", "garbage", "12 34 56", "x 1"])
def test_a_missing_or_broken_record_is_dropped(tmp_path: Path, text: str | None) -> None:
    if text is not None:
        (tmp_path / checks_guard.RECORD).write_text(text, encoding="utf-8")
    checks_guard.stop_stale(tmp_path)
    assert not (tmp_path / checks_guard.RECORD).exists()


def test_a_group_that_ignores_sigterm_is_killed_after_the_grace(tmp_path: Path) -> None:
    proc = _leader("bash", "-c", "trap '' TERM; sleep 30")  # an ignored signal stays ignored in sleep
    try:
        wait(lambda: _alive(proc.pid))
        time.sleep(0.2)  # let bash install the trap
        checks_guard.remember(tmp_path, proc.pid)
        reaper = threading.Thread(target=proc.wait, daemon=True)
        reaper.start()
        checks_guard.stop_stale(tmp_path, grace=0.3)
        reaper.join(5)
        assert proc.returncode == -signal.SIGKILL
    finally:
        if proc.poll() is None:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.wait()


def test_forget_keeps_a_newer_runs_record_and_remember_skips_a_gone_pid(tmp_path: Path) -> None:
    (tmp_path / checks_guard.RECORD).write_text("999999999 5\n", encoding="utf-8")
    checks_guard.forget(tmp_path, 123)
    assert (tmp_path / checks_guard.RECORD).exists()
    checks_guard.forget(tmp_path, 999999999)
    assert not (tmp_path / checks_guard.RECORD).exists()
    checks_guard.forget(tmp_path, 1)  # no record: nothing to do
    checks_guard.remember(tmp_path, 999999999)
    assert not (tmp_path / checks_guard.RECORD).exists()
    assert checks_guard.proc_stat(999999999) is None
