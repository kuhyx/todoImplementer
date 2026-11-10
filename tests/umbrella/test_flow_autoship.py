"""Umbrella children ship themselves once their checks pass; no Ship click waits for the rest (T1923)."""

from __future__ import annotations

from typing import Any

import pytest
from runnerfakes import Env
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner import stages
from todoimpl.runner.scheduler import Scheduler
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


def test_t1923_a_child_without_a_done_check_ships_when_green(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)  # the live children had no done_check at all
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIVE)
    try:
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    assert "- [x] kuhyx/alpha" in client.tasks[NOTE].body


def test_t1923_a_child_left_at_its_gate_ships_on_the_next_drive(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    new_checks = stages.HANDLERS["checks"]

    def old_checks(d: Any) -> str | None:  # a server from before T1923: a green child waited for Ship
        nxt = new_checks(d)
        d.state.auto_ship = False
        return "gate" if nxt == "shipping" else nxt

    sched, client = boot(world, 1, checks=CHECKS)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIVE)
    monkeypatch.setitem(stages.HANDLERS, "checks", old_checks)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    monkeypatch.setitem(stages.HANDLERS, "checks", new_checks)  # not undo(): it drops the world's env
    st.stage = "implement"  # the live umbrella still had rounds to run when its children reached the gate
    store.save(world.root / CARD, st)
    again = Scheduler(client, world.root, check_timeout=20)  # recovery requeues the umbrella
    try:
        at_rest(world, again, "shipped")
    finally:
        again.close()
    assert "- [x] kuhyx/alpha" in client.tasks[NOTE].body
