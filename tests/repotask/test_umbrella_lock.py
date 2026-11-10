"""The umbrella and the repo task share the per-repo lock: the one exception to one card per repo (T1912)."""

from __future__ import annotations

import sys
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "umbrella"))

from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.repolock import RepoLocks
from todoimpl.umbrella import children, run, view
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live

HOLDER = "3577d7fe-0"  # the repo task of kuhyx/alpha


@pytest.fixture
def free(world: Env, monkeypatch: pytest.MonkeyPatch) -> Iterator[Free]:
    outside = Free(world)
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", outside.url)
    yield outside
    outside.stop()


def until(check: Callable[[], bool], timeout: float = 30.0) -> None:
    end = time.time() + timeout
    while not check():
        assert time.time() < end, "condition not reached"
        time.sleep(0.05)


def child_stage(world: Env, cid: str) -> str | None:
    found = view.child_state(world.root / CARD, cid)
    return None if found is None else found.stage


def test_t1913_a_child_waits_for_its_repos_own_task_while_the_other_children_go_on(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "REPO_POLL", 0.05)
    sched, _ = boot(world, 2)  # alpha (umbr0001-1) comes first, beta (umbr0001-2) second
    world.script(NOTE, *manager("CHILD kuhyx/beta: clean"))
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 2)
    assert sched.locks.acquire("kuhyx/alpha", HOLDER) is None
    try:
        sched.start(CARD)
        until(lambda: child_stage(world, "umbr0001-2") == "gate")
        assert child_stage(world, "umbr0001-2") == "gate"
        assert child_stage(world, "umbr0001-1") is None  # alpha never started
        assert sched.lock_waits() == {"umbr0001-1": HOLDER}
        st = store.load(world.root / CARD)
        assert st is not None
        rows, _ = view.rows(world.root / CARD, st, live=True, limit_until=None, waits=sched.lock_waits())
        by_id = {row["id"]: row for row in rows}
        assert (by_id["umbr0001-1"]["status"], by_id["umbr0001-1"]["waits_on"]) == (
            "backlog",
            HOLDER,
        )  # not started yet; the page draws it queued
        assert "waits_on" not in by_id["umbr0001-2"]
        sched.locks.release(HOLDER)
        at_rest(world, sched, "gate")
        assert child_stage(world, "umbr0001-1") == "gate"
        assert sched.lock_waits() == {}
        assert sched.locks.free("kuhyx/alpha", "x")
        assert sched.locks.free("kuhyx/beta", "x")
    finally:
        sched.close()


def test_cancelling_the_umbrella_while_every_child_waits_ends_the_drive(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(run, "REPO_POLL", 0.05)
    sched, _ = boot(world, 1)
    assert sched.locks.acquire("kuhyx/alpha", HOLDER) is None
    try:
        sched.start(CARD)
        until(lambda: bool(sched.lock_waits()))
        assert sched.lock_waits() == {"umbr0001-1": HOLDER}
        sched.cancel(CARD)
        at_rest(world, sched, "cancelled")
        assert sched.lock_waits() == {}
    finally:
        sched.close()


def test_a_child_cancelled_while_it_waits_for_its_repo_never_runs() -> None:
    locks = RepoLocks()
    locks.acquire("kuhyx/a", "other-0")
    ran: list[str] = []
    pool = children.Pool.__new__(children.Pool)
    pool.detached = False
    pool.kids = {"aaaa1111-0": SimpleNamespace(repo="kuhyx/a")}  # type: ignore[dict-item]
    pool.ctx = SimpleNamespace(locks=locks, cancelled=lambda: True)  # type: ignore[assignment]
    driver = SimpleNamespace(state=SimpleNamespace(task_id="aaaa1111-0"), run=lambda: ran.append("ran"))
    pool._drive(driver)  # type: ignore[arg-type]
    assert ran == []
    assert locks.waits() == {}
    pool.ctx = SimpleNamespace(locks=locks, cancelled=lambda: False)  # type: ignore[assignment]
    locks.release("other-0")
    pool._drive(driver)  # type: ignore[arg-type]
    assert ran == ["ran"]
    assert locks.free("kuhyx/a", "x")  # the child let go of its repo when it ended
