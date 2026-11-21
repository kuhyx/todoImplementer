"""A build waiting in the ticket queue between flock tries is still a lock wait, not a job (T2429)."""

import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from todoimpl.runner import bgwait, buildlock, buildqueue


@pytest.fixture
def sleeper() -> Iterator[int]:
    proc = subprocess.Popen(["sleep", "30"])
    yield proc.pid
    proc.kill()
    proc.wait(timeout=10)


def _ticket(seq: int, pid: int, state: str) -> Path:
    queue = buildlock.root() / buildqueue.QUEUE
    queue.mkdir(parents=True, exist_ok=True)
    path = queue / f"{seq:012d}"
    path.write_text(f"{pid} {state} card-a (make -s test-shard) since 2026-11-21 09:00:00\n")
    return path


def test_t2429_a_queued_waiter_between_tries_is_seen(sleeper: int) -> None:
    _ticket(1, sleeper, "wait")
    assert sleeper in bgwait.waiters(buildlock.root() / buildlock.LOCK)


def test_t2429_a_holder_or_a_dead_owner_is_not_a_waiter(sleeper: int) -> None:
    _ticket(1, sleeper, "held")
    _ticket(2, 2**22 + 7, "wait")
    _ticket(3, 0, "junk")
    assert bgwait.waiters(buildlock.root() / buildlock.LOCK) == []
