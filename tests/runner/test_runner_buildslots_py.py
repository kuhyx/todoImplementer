"""The board's own checks with more than one build slot (T2419, T2420): `held` and the queue in Python."""

from __future__ import annotations

import fcntl
import threading
import time
from pathlib import Path
from typing import IO, Any

import pytest
from todoimpl.runner import buildlock, buildqueue


@pytest.fixture
def base(monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv(buildlock.SLOTS_VAR, "2")
    monkeypatch.setattr(buildqueue, "RECHECK", 0.1)
    root = buildlock.root()
    (root / buildqueue.QUEUE).mkdir(parents=True, exist_ok=True)
    return root


def _grab(path: Path) -> IO[Any]:
    fh = path.open("a")
    fcntl.flock(fh, fcntl.LOCK_EX)
    return fh


def _in_thread(done: list[str]) -> threading.Thread:
    def check() -> None:
        with buildlock.held("card-b", "cmake test", 0):
            done.append("held")

    thread = threading.Thread(target=check)
    thread.start()
    return thread


def test_t2419_a_check_waits_while_every_slot_is_held_by_hand_then_takes_slot_0(base: Path) -> None:
    slot0, slot1 = _grab(buildlock.slot_lock(base, 0)), _grab(buildlock.slot_lock(base, 1))
    done: list[str] = []
    thread = _in_thread(done)
    time.sleep(0.35)  # several timed looks at slot 0 come back empty
    assert done == []
    slot0.close()  # the timed look at slot 0 gets it
    thread.join(10)
    assert done == ["held"]
    slot1.close()


def test_t2420_a_check_goes_once_fewer_live_tickets_than_slots_are_ahead(
    base: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    queue = base / buildqueue.QUEUE
    ahead = []
    for seq in (1, 2):
        path = queue / f"{seq:012d}"
        path.write_text(f"1 held card-{seq} (cmake) since 2026-11-21 10:00:00\n")
        ahead.append(_grab(path))
    real = buildqueue._live_ahead
    gone = [queue / "000000000098", queue / "000000000099"]
    calls: list[int] = []

    def live_ahead(mine: Path, passed: set[str]) -> list[Path]:
        calls.append(1)
        return gone if len(calls) == 1 else real(mine, passed)  # a ticket removed under us is looked at again

    monkeypatch.setattr(buildqueue, "_live_ahead", live_ahead)
    done: list[str] = []
    thread = _in_thread(done)
    time.sleep(0.35)
    assert done == []
    ahead[0].close()  # the oldest ends, not the one right before: fewer than two are ahead now
    thread.join(10)
    assert done == ["held"]
    ahead[1].close()
