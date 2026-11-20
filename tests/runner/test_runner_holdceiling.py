"""The hold ceiling: a build-lock holder whose tree does nothing for 2 min gives the lock on (T2166)."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock, buildqueue, holdceiling

IDLE = '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\nexec sleep 30\n'
BUSY = (
    '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'
    "end=$((SECONDS + 3))\nwhile ((SECONDS < end)); do :; done\n"
)
QUICK = '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'


class Sink:
    """The scheduler's bus as the ceiling sees it."""

    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []
        self.bus = self

    def publish(self, card: str, event: dict[str, Any]) -> None:
        self.events.append((card, event))


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for name, text in (("cmake", IDLE), ("cargo", BUSY), ("go", QUICK)):
        executable(fakebin / name, text)
    return {
        **os.environ,
        "PATH": f"{shims}:{fakebin}:{os.environ['PATH']}",
        "BUILD_LOG": str(tmp_path / "log"),
    }


def _until(check: Any, what: str, limit: float = 15) -> None:
    deadline = time.monotonic() + limit
    while not check():
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.05)


def _log(env: dict[str, str]) -> str:
    path = Path(env["BUILD_LOG"])
    return path.read_text() if path.exists() else ""


def _ticks(ceiling: holdceiling.Ceiling, seconds: float) -> None:
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        ceiling.tick()
        time.sleep(0.1)


def _tick_until(ceiling: holdceiling.Ceiling, check: Any, what: str) -> None:
    deadline = time.monotonic() + 10
    while True:
        ceiling.tick()
        if check():
            return
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.05)


def _popen(argv: list[str], env: dict[str, str], tmp_path: Path, **kw: Any) -> subprocess.Popen[str]:
    return subprocess.Popen(argv, env=env, stderr=subprocess.PIPE, text=True, **kw)


def test_t2166_an_idle_holder_hands_the_lock_on_and_its_card_hears_it(
    env: dict[str, str], tmp_path: Path
) -> None:
    sink = Sink()
    ceiling = holdceiling.Ceiling(sink, quiet=0.6)
    idle = _popen(["cmake", "A"], {**env, buildlock.CARD_VAR: "card-a"}, tmp_path)
    _until(lambda: "start A" in _log(env), "start A")
    nxt = _popen(["go", "B"], {**env, buildlock.CARD_VAR: "card-b"}, tmp_path)
    _ticks(ceiling, 0.3)
    assert "start B" not in _log(env)  # not idle long enough yet
    _tick_until(ceiling, lambda: "start B" in _log(env), "the next build running")
    assert nxt.wait(timeout=10) == 0
    assert idle.poll() is None  # the idle build is never killed, it just runs on without the lock
    idle.terminate()
    _, err = idle.communicate(timeout=10)
    assert "buildlock: released the build lock: cmake A did nothing for 2 min" in err
    ((card, event),) = sink.events
    assert card == "card-a"
    assert event["type"] == "activity"
    assert event["kind"] == "system"
    assert event["text"].startswith(
        "build lock taken back from cmake A: no CPU, disk or new process for 0.6 s"
    )
    assert (buildlock.root() / buildlock.HOLDER).read_text() == ""


def test_t2166_a_busy_holder_keeps_the_lock(env: dict[str, str], tmp_path: Path) -> None:
    sink = Sink()
    ceiling = holdceiling.Ceiling(sink, quiet=0.6)
    busy = _popen(["cargo", "A"], {**env, buildlock.CARD_VAR: "card-a"}, tmp_path)
    _until(lambda: "start A" in _log(env), "start A")
    _ticks(ceiling, 1.5)
    assert busy.poll() is None
    assert [t.state for t in buildqueue.listing(buildlock.root())] == ["held"]
    assert busy.wait(timeout=20) == 0
    assert sink.events == []


def test_t2166_a_card_less_holder_is_named_by_its_run_dir_and_a_bare_sink_only_logs(
    env: dict[str, str], tmp_path: Path
) -> None:
    run_wt = buildlock.root() / "c1-0" / "wt"
    run_wt.mkdir(parents=True)
    sink = Sink()
    ceiling = holdceiling.Ceiling(sink, quiet=0.3)
    idle = _popen(["cmake", "A"], env, tmp_path, cwd=run_wt)
    _until(lambda: "start A" in _log(env), "start A")
    _tick_until(ceiling, lambda: bool(sink.events), "the cut")
    assert sink.events[0][0] == "c1-0"
    idle.kill()
    idle.wait(timeout=10)
    outside = _popen(["cmake", "B"], env, tmp_path, cwd=tmp_path)
    _until(lambda: "start B" in _log(env), "start B")
    bare = holdceiling.Ceiling(object(), quiet=0.3)
    _tick_until(bare, lambda: not buildqueue.listing(buildlock.root()), "the second cut")
    outside.kill()
    outside.wait(timeout=10)


def test_t2166_the_boards_own_checks_and_foreign_holders_are_left_alone(tmp_path: Path) -> None:
    sink = Sink()
    ceiling = holdceiling.Ceiling(sink, quiet=0.0)
    ready, done = threading.Event(), threading.Event()

    def board() -> None:
        with buildlock.held("card-board", "cmake test", 0):
            ready.set()
            done.wait(10)

    thread = threading.Thread(target=board)
    thread.start()
    ready.wait(10)
    _ticks(ceiling, 0.3)  # the server's own pid: a USR1 would kill this very test
    done.set()
    thread.join(10)
    sleeper = subprocess.Popen(["sleep", "30"])
    base = buildlock.root()
    queue = base / buildqueue.QUEUE
    with (queue / "000000000050").open("w") as fh:
        fh.write(f"{sleeper.pid} held ? (sleep) since 2026-11-19 10:00:00\n")
        fh.flush()
        import fcntl  # noqa: PLC0415 - only this test holds a ticket by hand

        fcntl.flock(fh, fcntl.LOCK_EX)
        _ticks(ceiling, 0.3)
    assert sleeper.poll() is None
    sleeper.kill()
    sleeper.wait()
    assert sink.events == []


def test_t2166_the_thread_starts_once_and_stops(monkeypatch: pytest.MonkeyPatch) -> None:
    ticks: list[int] = []
    ceiling = holdceiling.Ceiling(Sink(), every=0.01)

    def tick() -> None:
        ticks.append(1)
        raise OSError("boom")

    monkeypatch.setattr(ceiling, "tick", tick)
    ceiling.start()
    ceiling.start()
    _until(lambda: len(ticks) >= 2, "two ticks")
    ceiling.stop()
    holdceiling.Ceiling(Sink()).stop()
