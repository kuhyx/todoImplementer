"""A restart while a child was shipping: no blind second Ship; Retry puts the child back at the gate."""

from __future__ import annotations

from typing import Any

from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella.children import fresh_state
from todoimpl.umbrella.note import children
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, NOTE, at_rest, boot


def _seed(world: Env, client: Any, stage: str) -> str:
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
    store.save(world.root / CARD, store.RunState(task_id=CARD, stage="implement", extra={"umbrella": record}))
    return kid.cid


def test_t1905_a_child_found_mid_ship_after_a_restart_is_not_shipped_again_blindly(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "shipping")
    again = Scheduler(client, world.root, check_timeout=20)  # recovery requeues the interrupted umbrella
    try:
        st = at_rest(world, again, "failed")
    finally:
        again.close()
    child = store.load(child_dir(world.root / CARD, cid))
    assert child is not None
    assert (child.stage, child.extra["failed_stage"]) == ("failed", "gate")
    assert "interrupted by a restart" in str(child.error)
    assert "1 of 1 children need you" in str(st.error)
    assert not [c for c in world.calls() if str(c["cwd"]).endswith("wt")]  # nothing ran in the child


def test_t1905_retry_puts_the_interrupted_child_back_at_the_gate(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "shipping")
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        at_rest(world, again, "failed")
        again.start(CARD)
        st = at_rest(world, again, "gate")
    finally:
        again.close()
    child = store.load(child_dir(world.root / CARD, cid))
    assert child is not None
    assert child.stage == "gate"
    assert st.error is None
