"""The build lock's ticket queue: waiters run in arrival order, dead tickets never block it (T2164)."""

from __future__ import annotations

import contextlib
import fcntl
import os
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import bgwait, buildlock, buildqueue

if TYPE_CHECKING:
    from collections.abc import Iterator

# A fake build: logs its start, waits for its go file (the holder) or not at all, then logs its end.
GATED = (
    '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'
    'while [[ -n "${GO_FILE:-}" && ! -e "$GO_FILE" ]]; do sleep 0.02; done\necho "end $1" >> "$BUILD_LOG"\n'
)
WAITERS = 6


@pytest.fixture
def world(tmp_path: Path) -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    executable(fakebin / "cmake", GATED)
    path = f"{shims}:{fakebin}:{os.environ['PATH']}"
    return {**os.environ, "PATH": path, "BUILD_LOG": str(tmp_path / "builds.log")}


def _log(env: dict[str, str]) -> list[str]:
    path = Path(env["BUILD_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def _until(check: object, what: str) -> None:
    deadline = time.monotonic() + 15
    while not callable(check) or not check():
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.02)


def _blocked() -> int:
    """Count the flock requests blocked on the build lock or on any ticket of the temp lock root."""
    return len(bgwait.waiters(buildlock.root() / buildlock.LOCK))


def _start(env: dict[str, str], name: str, tmp_path: Path, **extra: str) -> subprocess.Popen[bytes]:
    err = (tmp_path / f"{name}.err").open("w")
    return subprocess.Popen(
        ["cmake", name], env={**env, buildlock.CARD_VAR: f"card-{name}", **extra}, stderr=err
    )


def _queue_up(env: dict[str, str], tmp_path: Path, names: list[str]) -> list[subprocess.Popen[bytes]]:
    """Start each waiter only once the one before it blocks, so the arrival order is certain."""
    procs = []
    for name in names:
        before = _blocked()
        procs.append(_start(env, name, tmp_path))
        _until(lambda b=before: _blocked() > b, f"{name} blocking")
    return procs


def test_t2164_waiters_run_in_the_order_they_arrived(world: dict[str, str], tmp_path: Path) -> None:
    go = tmp_path / "go"
    holder = _start({**world, "GO_FILE": str(go)}, "H", tmp_path)
    _until(lambda: "start H" in _log(world), "start H")
    names = [f"W{i}" for i in range(WAITERS)]
    procs = _queue_up(world, tmp_path, names)
    go.touch()
    for proc in [holder, *procs]:
        assert proc.wait(timeout=30) == 0
    assert [line for line in _log(world) if line.startswith("start")] == ["start H"] + [
        f"start {n}" for n in names
    ]
    assert "1 ahead" in (tmp_path / "W0.err").read_text()
    assert "2 ahead" in (tmp_path / "W1.err").read_text()
    assert not list(buildqueue.tickets(buildlock.root()))


def _tree(pid: int) -> list[int]:
    kids = [int(k) for k in open(f"/proc/{pid}/task/{pid}/children").read().split()]  # noqa: PTH123, SIM115
    return [pid] + [p for kid in kids for p in _tree(kid)]


def test_t2164_a_later_arrival_never_overtakes_a_waiter_slow_to_wake(
    world: dict[str, str], tmp_path: Path
) -> None:
    """On a loaded PC a woken waiter can be slow to run; a newcomer must not take the lock in that gap."""
    go = tmp_path / "go"
    holder = _start({**world, "GO_FILE": str(go)}, "H", tmp_path)
    _until(lambda: "start H" in _log(world), "start H")
    (slow,) = _queue_up(world, tmp_path, ["SLOW"])
    stopped = _tree(slow.pid)
    for pid in stopped:
        os.kill(pid, signal.SIGSTOP)
    go.touch()
    assert holder.wait(timeout=30) == 0
    late = _start(world, "LATE", tmp_path)
    time.sleep(0.5)  # the newcomer has every chance to jump the queue now
    for pid in stopped:
        os.kill(pid, signal.SIGCONT)
    assert (slow.wait(timeout=30), late.wait(timeout=30)) == (0, 0)
    assert [line for line in _log(world) if line.startswith("start")] == [
        "start H",
        "start SLOW",
        "start LATE",
    ]


def test_t2164_a_killed_waiter_and_a_stale_ticket_never_block_the_queue(
    world: dict[str, str], tmp_path: Path
) -> None:
    base = buildlock.root()
    queue = base / buildqueue.QUEUE
    queue.mkdir(parents=True, exist_ok=True)
    (queue / "000000000001").write_text(
        "999999 wait ? (cmake old) since 2026-11-19 10:00:00\n"
    )  # after a reboot
    go = tmp_path / "go"
    holder = _start({**world, "GO_FILE": str(go)}, "H", tmp_path)
    _until(lambda: "start H" in _log(world), "start H")
    first, middle, last = _queue_up(world, tmp_path, ["A", "B", "C"])
    middle.send_signal(signal.SIGKILL)
    assert middle.wait(timeout=5) == -signal.SIGKILL
    go.touch()
    for proc in (holder, first, last):
        assert proc.wait(timeout=30) == 0
    assert [line for line in _log(world) if line.startswith("start")] == ["start H", "start A", "start C"]
    assert not list(buildqueue.tickets(base))


def test_t2164_the_board_and_the_shims_share_one_queue(world: dict[str, str], tmp_path: Path) -> None:
    go = tmp_path / "go"
    holder = _start({**world, "GO_FILE": str(go)}, "H", tmp_path)
    _until(lambda: "start H" in _log(world), "start H")
    (first,) = _queue_up(world, tmp_path, ["A"])
    before = _blocked()
    order: list[str] = []

    def board() -> None:
        with buildlock.held("card-board", "cmake test", 0):
            order.append("board")
            with open(world["BUILD_LOG"], "a") as log:  # noqa: PTH123 - same log as the fake builds
                log.write("start board\n")

    thread = threading.Thread(target=board)
    thread.start()
    _until(lambda: _blocked() > before, "the board blocking")
    (last,) = _queue_up(world, tmp_path, ["C"])
    go.touch()
    thread.join(30)
    for proc in (holder, first, last):
        assert proc.wait(timeout=30) == 0
    assert [line for line in _log(world) if line.startswith("start")] == [
        "start H", "start A", "start board", "start C",
    ]  # fmt: skip


@contextlib.contextmanager
def _ticket_held(base: Path, name: str, text: str) -> Iterator[None]:
    queue = base / buildqueue.QUEUE
    queue.mkdir(parents=True, exist_ok=True)
    with (queue / name).open("w") as fh:
        fh.write(text)
        fh.flush()
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def test_t2164_the_queue_lists_live_tickets_in_order_and_drops_stale_ones(tmp_path: Path) -> None:
    base = buildlock.root()
    buildlock.ensure(base)
    (base / buildqueue.QUEUE).mkdir(parents=True, exist_ok=True)
    (base / buildqueue.QUEUE / "000000000003").write_text("1 wait ? (cmake dead) since 2026-11-19 10:00:00\n")
    (base / buildqueue.QUEUE / ".new.77").write_text("")
    with (
        _ticket_held(
            base, "000000000002", f"{os.getpid()} held card-a (cmake a) since 2026-11-19 10:00:01\n"
        ),
        _ticket_held(base, "000000000005", "12 wait card-b (flutter build apk) since 2026-11-19 10:00:02\n"),
        _ticket_held(base, "000000000009", "garbage"),
    ):
        listed = buildqueue.listing(base)
        assert [(t.seq, t.pid, t.state, t.card, t.command) for t in listed] == [
            (2, os.getpid(), "held", "card-a", "cmake a"),
            (5, 12, "wait", "card-b", "flutter build apk"),
            (9, 0, "wait", "?", ""),
        ]
        shown = subprocess.run(
            [str(base / buildlock.WRAPPER), "--queue"], capture_output=True, text=True, timeout=5, check=True
        ).stdout.splitlines()
        assert shown[0].startswith("1 held card-a (cmake a) since 2026-11-19 10:00:01 pid ")
        assert shown[1] == "2 wait card-b (flutter build apk) since 2026-11-19 10:00:02 pid 12"
        assert len(shown) == 3
    assert not (base / buildqueue.QUEUE / "000000000003").exists()
    assert buildqueue.listing(tmp_path / "none") == []


def test_t2164_a_waiter_on_a_ticket_counts_as_a_build_lock_waiter(tmp_path: Path) -> None:
    base = buildlock.root()
    buildlock.ensure(base)
    with _ticket_held(base, "000000000001", "1 held ? (x) since 2026-11-19 10:00:00\n"):
        waiter = subprocess.Popen(["flock", str(base / buildqueue.QUEUE / "000000000001"), "true"])
        _until(lambda: waiter.pid in bgwait.waiters(base / buildlock.LOCK), "the waiter in /proc/locks")
    assert waiter.wait(timeout=5) == 0
