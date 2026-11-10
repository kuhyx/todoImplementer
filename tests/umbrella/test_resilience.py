"""A killed or cut-off umbrella manager is retried with backoff; its children are never escalated."""

from __future__ import annotations

from runnerfakes import Env
from tierfakes import Free
from todoimpl.runner import retry
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live

KILL = ({"_fake": "exit", "code": 247},)  # 128 + 119: a signal ended claude, no result event


def test_t1902_a_killed_manager_is_retried_and_its_children_are_not_escalated(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *KILL)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    (row,) = st.extra["umbrella"]["rounds"][0]["children"]
    assert (row["verdict"], row["ok"]) == ("clean", True)
    assert st.extra["umbrella"]["width"] == 2


def test_t1902_a_manager_killed_past_the_bound_fails_the_umbrella_without_escalating(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1)
    for _ in range(retry.MAX_KILL_RETRIES + 1):
        world.script(NOTE, *KILL)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
    finally:
        sched.close()
    assert st.error is not None
    assert st.error.startswith("The implement turn failed")
    assert st.extra["umbrella"]["rounds"] == []
