"""A board check waiting on the build lock keeps its place in the queue across a server restart (T2168)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest
from runnerfakes import executable
from todoimpl.runner import bgwait, buildlock, buildqueue

GATED = (
    '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'
    'while [[ -n "${GO_FILE:-}" && ! -e "$GO_FILE" ]]; do sleep 0.02; done\n'
)
# The server's check: wait for the lock in `held`, then log its start, as checks.run_capped would run it.
BOARD = (
    "import sys\nfrom todoimpl.runner import buildlock\n"
    "with buildlock.held(sys.argv[1], sys.argv[2], 0):\n"
    "    open(sys.argv[3], 'a').write('start board\\n')\n"
)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    executable(fakebin / "cmake", GATED)
    path = f"{shims}:{fakebin}:{os.environ['PATH']}"
    return {**os.environ, "PATH": path, "BUILD_LOG": str(tmp_path / "builds.log")}


def _starts(env: dict[str, str]) -> list[str]:
    path = Path(env["BUILD_LOG"])
    return [x for x in path.read_text().splitlines() if x.startswith("start")] if path.exists() else []


def _until(check: object, what: str) -> None:
    deadline = time.monotonic() + 15
    while not (callable(check) and check()):
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.02)


def _queued(proc: subprocess.Popen[bytes]) -> bool:
    """Say whether `proc` holds its `wait` ticket: one pid per waiter, never its flock child too (T2499)."""
    return proc.pid in bgwait.queued(buildlock.root())


def _board(env: dict[str, str], card: str = "c1-0", command: str = "cmake test") -> subprocess.Popen[bytes]:
    server = str(Path(buildlock.__file__).parents[2])  # the package dir, as the server runs it
    argv = [sys.executable, "-c", BOARD, card, command, env["BUILD_LOG"]]
    return subprocess.Popen(argv, env={**env, "PYTHONPATH": server})


def _make(env: dict[str, str], name: str, **extra: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(["cmake", name], env={**env, **extra})


def test_t2168_a_check_killed_by_a_restart_comes_back_to_its_place(
    env: dict[str, str], tmp_path: Path
) -> None:
    go = tmp_path / "go"
    holder = _make(env, "H", GO_FILE=str(go))
    _until(lambda: _starts(env) == ["start H"], "start H")
    old = _board(env)
    _until(lambda: _queued(old), "the check queueing")
    later = _make(env, "W")
    _until(lambda: _queued(later), "W queueing")
    old.send_signal(signal.SIGKILL)  # the server restarts (deploy): its waiting check dies
    old.wait(timeout=5)
    time.sleep(0.3)  # W wakes on the dead ticket and must not take its place
    new = _board(env)  # the new server runs the same check again
    time.sleep(0.3)
    go.touch()
    for proc in (holder, new, later):
        assert proc.wait(timeout=30) == 0
    assert _starts(env) == ["start H", "start board", "start W"]
    assert buildqueue.tickets(buildlock.root()) == []


def test_t2168_an_unclaimed_place_expires_and_other_checks_take_new_tickets(
    env: dict[str, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = buildlock.root()
    queue = base / buildqueue.QUEUE
    queue.mkdir(parents=True)
    kept = queue / "000000000001"
    kept.write_text("99 wait c1-0 (cmake test) since 2026-11-19 10:00:00 board\n")
    other = queue / "000000000002"
    other.write_text("99 gone c2-0 (cmake lint) since 2026-11-19 10:00:00 board\n")
    os.utime(other, (time.time() - buildqueue.RESERVE - 1,) * 2)
    plain = queue / "000000000003"
    plain.write_text("98 wait ? (cmake x) since 2026-11-19 10:00:00\n")
    assert buildqueue.listing(base) == []
    assert kept.read_text().split()[1] == "gone"  # stamped: its place is kept for RESERVE s from now
    assert not other.exists()  # unclaimed for too long
    assert not plain.exists()  # a session's ticket has no place to come back to
    shown = subprocess.run(
        [str(base / buildlock.WRAPPER), "--queue"], capture_output=True, text=True, timeout=5, check=True
    )
    assert (shown.stdout, kept.exists()) == ("", True)
    with buildlock.held("c3-0", "cmake other", 0):  # another check never takes c1-0's place
        assert kept.exists()
    done = subprocess.run(["cmake", "Q"], env=env, timeout=10, check=False)  # a session build passes it by
    assert done.returncode == 0
    assert kept.exists()
    with buildlock.held("c1-0", "cmake test", 0):
        assert buildqueue.listing(base)[0].seq == 1
    assert not kept.exists()
