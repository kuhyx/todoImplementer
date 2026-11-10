"""Restarts: a round resumes at the step it reached; a cancelled umbrella restarts its cancelled children."""

from __future__ import annotations

from typing import Any

from runnerfakes import Env
from schedfakes import wait
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella.children import fresh_state
from todoimpl.umbrella.note import children
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, manager


def test_a_round_with_verdicts_and_checks_saved_does_not_run_the_manager_again(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    (kid,) = children(client.tasks[NOTE].body, NOTE)
    child = fresh_state(kid, 1, 0.0, auto_ship=False)
    child.extra.update(free=True)
    store.save(child_dir(world.root / CARD, kid.cid), child)
    current = {
        "n": 1, "width": 1, "ids": [kid.cid], "started": 0.0, "free": {kid.cid: True}, "failed": {},
        "verdicts": {kid.cid: {"kind": "clean", "detail": ""}}, "checks": {kid.cid: True},
    }  # fmt: skip
    record: dict[str, Any] = {"width": 1, "tier": None, "kids": [], "rounds": [], "current": current}
    store.save(world.root / CARD, store.RunState(task_id=CARD, stage="implement", extra={"umbrella": record}))
    world.script("umbr0001-1", *LIVE)
    again = Scheduler(client, world.root, check_timeout=20)  # recovery requeues the interrupted umbrella
    try:
        st = at_rest(world, again, "gate")
    finally:
        again.close()
    assert not [c for c in world.calls() if "Umbrella manager" in str(c["prompt"])]
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["ok"] is True
    assert st.extra["umbrella"]["current"] is None


def test_restarting_a_cancelled_umbrella_restarts_its_cancelled_child(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", {"_fake": "sleep", "sec": 30}, *LIVE)
    try:
        sched.start(CARD)
        wait(lambda: any(c["cwd"].endswith("umbr0001-1/wt") for c in world.calls()))
        sched.cancel(CARD)
        at_rest(world, sched, "cancelled")
        world.script("umbr0001-1", {"_fake": "result", "text": "C1: done\n\nD: done"})
        world.script("umbr0001-1", *LIVE)
        sched.start(CARD)
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    assert st.error is None
