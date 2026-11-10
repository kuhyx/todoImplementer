"""Umbrella children ship themselves once their checks pass; no Ship click waits for the rest (T1923)."""

from __future__ import annotations

from typing import Any

import pytest
from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella import children, rounds
from umbrellarig import CARD, NOTE, at_rest, boot, manager

CHECKS = {"alpha": "true"}  # green at the round, so the next turn is the live check
LIVE = (
    {"_fake": "write", "path": "hello.txt", "text": "hi\n"},
    {"_fake": "result", "text": "- [x] C1: ran it -> saw it\n- [x] C2: ran the check -> ok\n\nD: done"},
)


def test_t1923_a_new_child_ships_by_itself_when_its_checks_pass(world: Env, free: Free) -> None:
    sched, client = boot(world, 1, checks=CHECKS)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIVE)
    try:
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    child = store.load(world.root / CARD / "children" / "umbr0001-1")
    assert child is not None
    assert (child.stage, child.auto_ship) == ("shipped", True)
    assert "- [x] kuhyx/alpha" in client.tasks[NOTE].body


def test_t1923_a_child_left_at_its_gate_ships_on_the_next_drive(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_child = rounds.fresh_state
    def old_child(*a: Any, **kw: Any) -> store.RunState:  # a child from before T1923: it waited for Ship
        return children.fresh_state(*a, **{**kw, "auto_ship": False})

    sched, client = boot(world, 1, checks=CHECKS)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIVE)
    monkeypatch.setattr(rounds, "fresh_state", old_child)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    monkeypatch.setattr(rounds, "fresh_state", new_child)  # not undo(): that would drop the world's env too
    st.stage = "implement"  # the live umbrella still had rounds to run when its children reached the gate
    store.save(world.root / CARD, st)
    again = Scheduler(client, world.root, check_timeout=20)  # recovery requeues the umbrella
    try:
        at_rest(world, again, "shipped")
    finally:
        again.close()
    assert "- [x] kuhyx/alpha" in client.tasks[NOTE].body
