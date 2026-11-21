"""Three builds at once (kuhy, 2026-11-21): `SLOTS` build-lock places, still taken in arrival order."""

from __future__ import annotations

import fcntl
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest
from runnerfakes import executable
from todoimpl.runner import bgwait, buildlock, buildqueue, holdceiling

# A fake build: logs its start, waits for its own go file, then logs its end.
GATED = (
    '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'
    'while [[ ! -e "$GO_DIR/$1" ]]; do sleep 0.02; done\necho "end $1" >> "$BUILD_LOG"\n'
)
IDLE = '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\nexec sleep 30\n'


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    monkeypatch.setenv(buildlock.SLOTS_VAR, "3")
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    executable(fakebin / "cmake", GATED)
    executable(fakebin / "cargo", IDLE)
    (tmp_path / "go").mkdir()
    return {
        **os.environ,
        "PATH": f"{shims}:{fakebin}:{os.environ['PATH']}",
        "BUILD_LOG": str(tmp_path / "builds.log"),
        "GO_DIR": str(tmp_path / "go"),
    }


def _log(env: dict[str, str]) -> list[str]:
    path = Path(env["BUILD_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def _until(check: Any, what: str) -> None:
    deadline = time.monotonic() + 15
    while not check():
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.02)


def _start(env: dict[str, str], tool: str, name: str) -> subprocess.Popen[bytes]:
    return subprocess.Popen(
        [tool, name], env={**env, buildlock.CARD_VAR: f"card-{name}"}, stderr=subprocess.DEVNULL
    )


def _started(env: dict[str, str]) -> list[str]:
    return [line.split()[1] for line in _log(env) if line.startswith("start")]


def test_t2419_three_builds_run_at_once_and_a_fourth_waits(world: dict[str, str], tmp_path: Path) -> None:
    procs = []
    for name in ("A", "B", "C"):
        procs.append(_start(world, "cmake", name))
        _until(lambda n=name: n in _started(world), f"start {name}")
    procs.append(_start(world, "cmake", "D"))
    time.sleep(0.6)
    assert _started(world) == ["A", "B", "C"]
    holders = sorted((buildlock.root()).glob("build.lock*.holder"))
    assert len([h for h in holders if h.read_text().strip()]) == 3
    for name in ("A", "B", "C", "D"):
        (tmp_path / "go" / name).touch()
    assert [p.wait(timeout=30) for p in procs] == [0, 0, 0, 0]
    assert _started(world) == ["A", "B", "C", "D"]


def test_t2420_a_waiter_starts_when_any_holder_ends_not_just_the_one_before_it(
    world: dict[str, str], tmp_path: Path
) -> None:
    procs = []
    for name in ("A", "B", "C"):
        procs.append(_start(world, "cmake", name))
        _until(lambda n=name: n in _started(world), f"start {name}")
    procs.append(_start(world, "cmake", "D"))
    time.sleep(0.3)
    (tmp_path / "go" / "A").touch()  # the oldest ends; C, right before D, still runs
    _until(lambda: "D" in _started(world), "D starting while B and C run")
    for name in ("B", "C", "D"):
        (tmp_path / "go" / name).touch()
    assert [p.wait(timeout=30) for p in procs] == [0, 0, 0, 0]


def test_t2421_a_board_check_takes_a_free_slot_and_names_every_holder(
    world: dict[str, str], tmp_path: Path
) -> None:
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    (base / buildlock.HOLDER).write_text("card-x (cmake) since 2026-01-01 10:00:00\n")
    with (base / buildlock.LOCK).open("a") as slot0:
        fcntl.flock(slot0, fcntl.LOCK_EX)
        with buildlock.held("card-b", "cmake test", 0):  # slot 0 is busy, slot 1 is free: no wait
            assert (base / f"{buildlock.LOCK}.1.holder").read_text().startswith("card-b (cmake test)")
            assert bgwait.holder(base / buildlock.LOCK)[0] == "card-x"
        assert (base / f"{buildlock.LOCK}.1.holder").read_text() == ""


def test_t2421_a_waiter_on_any_slot_file_is_seen(world: dict[str, str], tmp_path: Path) -> None:
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    slot2 = base / f"{buildlock.LOCK}.2"
    with slot2.open("a") as held:
        fcntl.flock(held, fcntl.LOCK_EX)
        waiter = subprocess.Popen(["flock", str(slot2), "true"])
        try:
            _until(lambda: waiter.pid in bgwait.waiters(base / buildlock.LOCK), "the slot-2 waiter seen")
        finally:
            fcntl.flock(held, fcntl.LOCK_UN)
            waiter.wait(timeout=10)


def test_t2422_the_hold_ceiling_cuts_a_quiet_holder_that_is_not_first(
    world: dict[str, str], tmp_path: Path
) -> None:
    busy = _start(world, "cmake", "A")
    _until(lambda: "A" in _started(world), "start A")
    idle = _start(world, "cargo", "B")
    _until(lambda: "B" in _started(world), "start B")
    ceiling = holdceiling.Ceiling(object(), quiet=0.4)

    def cut() -> bool:
        ceiling.tick()
        return len(buildqueue.listing(buildlock.root())) == 1

    try:
        _until(cut, "the idle second holder cut")
    finally:
        (tmp_path / "go" / "A").touch()
        idle.kill()
        idle.wait(timeout=10)
    assert busy.wait(timeout=30) == 0


def test_t2421_a_hand_held_flock_on_a_slot_holder_is_refused(world: dict[str, str]) -> None:
    holder = buildlock.root() / f"{buildlock.LOCK}.2.holder"
    argv = ["flock", str(holder), "true"]
    done = subprocess.run(argv, env=world, capture_output=True, text=True, check=False)
    assert done.returncode == 2
    assert "refusing flock on the build lock's holder" in done.stderr
