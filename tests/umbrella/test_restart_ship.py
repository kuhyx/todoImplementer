"""A restart while a child was shipping: the child ships again by itself, a few times at most (T1988)."""

from __future__ import annotations

from typing import Any

import pytest
from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.repolock import RepoLocks
from todoimpl.runner.restart import MAX_RESUMES
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella.children import fresh_state
from todoimpl.umbrella.note import children
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, NOTE, at_rest, boot


def _seed(world: Env, client: Any, stage: str, parent: str = "implement") -> str:
    """Save an umbrella a restart finds mid-run with its one child already in `stage`."""
    (kid,) = children(client.tasks[NOTE].body, NOTE)
    child = fresh_state(kid, 1, 0.0, auto_ship=False)
    child.stage = stage
    store.save(child_dir(world.root / CARD, kid.cid), child)
    kids = [{"id": kid.cid, "repo": kid.repo, "title": kid.title, "done": False}]
    row = {"id": kid.cid, "verdict": "clean", "detail": "", "free": True, "checks": True, "ok": True}
    record = {
        "width": 2, "tier": None, "kids": kids, "current": None,
        "rounds": [{"n": 1, "width": 1, "next": 2, "children": [row]}],
    }  # fmt: skip
    store.save(world.root / CARD, store.RunState(task_id=CARD, stage=parent, extra={"umbrella": record}))
    return kid.cid


def _after_restart(world: Env, client: Any, cid: str, stage: str) -> store.RunState:
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        at_rest(world, again, stage)
    finally:
        again.close()
    child = store.load(child_dir(world.root / CARD, cid))
    assert child is not None
    return child


def test_t1988_a_child_found_mid_ship_after_a_restart_ships_again_by_itself(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "shipping")
    child = _after_restart(world, client, cid, "shipped")
    assert (child.stage, child.error) == ("shipped", None)
    assert child.extra["ship_resumes"] == 1


def test_t1905_a_child_cut_again_and_again_stops_with_the_interrupted_text_and_retry_ships_it(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "shipping")
    stuck = store.load(child_dir(world.root / CARD, cid))
    assert stuck is not None
    stuck.extra["ship_resumes"] = MAX_RESUMES
    store.save(child_dir(world.root / CARD, cid), stuck)
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        st = at_rest(world, again, "failed")
        child = store.load(child_dir(world.root / CARD, cid))
        assert child is not None
        assert (child.stage, child.extra["failed_stage"]) == ("failed", "shipping")
        assert str(child.error).startswith("Ship was interrupted by a restart")
        assert "1 of 1 children need you" in str(st.error)
        again.start(CARD)  # Retry: no second Ship click
        at_rest(world, again, "shipped")
    finally:
        again.close()
    done = store.load(child_dir(world.root / CARD, cid))
    assert done is not None
    assert (done.stage, done.error) == ("shipped", None)


def test_t1988_retry_sends_a_child_a_pre_fix_restart_failed_straight_to_ship(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "failed")
    old = store.load(child_dir(world.root / CARD, cid))
    assert old is not None
    old.extra["failed_stage"] = "gate"  # the form a restart left before T1988
    old.error = "Ship was interrupted by a restart: check origin and the note before shipping again"
    store.save(child_dir(world.root / CARD, cid), old)
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        at_rest(world, again, "failed")
        again.start(CARD)
        at_rest(world, again, "shipped")
    finally:
        again.close()


def test_t1988_an_umbrella_kuhy_clicked_ship_on_ships_its_children_again_after_a_restart(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "gate", parent="shipping")
    child = _after_restart(world, client, cid, "shipped")
    assert child.error is None
    parent = store.load(world.root / CARD)
    assert parent is not None
    assert "ship_resumes" not in parent.extra  # the children count their own resumes


def test_t2463_a_cut_ship_does_not_wait_for_another_run_of_its_repo_nor_burn_its_resumes(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "shipping")
    (kid,) = children(client.tasks[NOTE].body, NOTE)
    plain = RepoLocks.__init__

    def busy(self: RepoLocks) -> None:
        plain(self)
        self.acquire(kid.repo, "other-run")  # another run of the repo grabbed it first after the restart

    monkeypatch.setattr(RepoLocks, "__init__", busy)
    child = _after_restart(world, client, cid, "shipped")  # red before: it queued behind other-run
    assert (child.stage, child.error) == ("shipped", None)
    assert child.extra["ship_resumes"] == 1
