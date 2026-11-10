"""Umbrella drives that pause, are cancelled, lose a child at Ship, or cannot close the note."""

from __future__ import annotations

import time

from runnerfakes import Env
from schedfakes import lift_limit, reply, wait
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.umbrella import issues
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, dump, manager, script_live

LIMIT = (
    {"_fake": "limit", "resets_at": time.time() + 3600},
    {"_fake": "result", "text": "usage limit reached", "is_error": True},
)


def test_a_child_hitting_the_plan_limit_pauses_the_umbrella_and_it_goes_on_after(
    world: Env, free: Free
) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *LIMIT)
    world.script("umbr0001-1", *LIVE)
    try:
        sched.start(CARD)
        at_rest(world, sched, "paused_limit")
        child = store.load(world.root / CARD / "children" / "umbr0001-1")
        assert child is not None
        assert child.stage == "paused_limit"
        lift_limit(world, sched)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()


def test_a_child_retrying_a_failed_turn_pauses_the_umbrella_on_the_same_timer(world: Env, free: Free) -> None:
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", *reply("API Error: 500 overloaded", is_error=True))
    world.script("umbr0001-1", *LIVE)
    try:
        sched.start(CARD)
        at_rest(world, sched, "shipped")
    finally:
        sched.close()
    feed = (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")
    assert "paused_retry" in feed


def test_cancel_stops_the_manager_and_cancels_the_umbrella(world: Env, free: Free) -> None:
    sched, client = boot(world, 2)
    world.script(NOTE, {"_fake": "sleep", "sec": 30}, *manager("CHILD kuhyx/alpha: clean"))
    try:
        sched.start(CARD)
        wait(lambda: any("Umbrella manager" in str(c["prompt"]) for c in world.calls()))
        sched.cancel(CARD)
        at_rest(world, sched, "cancelled")
    finally:
        sched.close()
    assert client.abandoned == [CARD]


def test_cancel_between_rounds_is_noticed(world: Env, free: Free) -> None:
    sched, _ = boot(world, 3)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", {"_fake": "sleep", "sec": 30}, *LIVE)
    try:
        sched.start(CARD)
        wait(lambda: any(c["cwd"].endswith("umbr0001-1/wt") for c in world.calls()))
        sched.cancel(CARD)
        at_rest(world, sched, "cancelled")
        child = store.load(world.root / CARD / "children" / "umbr0001-1")
        assert child is not None
        assert child.stage == "cancelled"
    finally:
        sched.close()


def test_closing_the_server_mid_child_turn_leaves_the_run_resumable(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    world.script("umbr0001-1", {"_fake": "sleep", "sec": 2}, *LIVE)
    sched.start(CARD)
    wait(lambda: any(c["cwd"].endswith("umbr0001-1/wt") for c in world.calls()))
    sched.close()
    child = store.load(world.root / CARD / "children" / "umbr0001-1")
    assert child is not None
    assert child.stage == "live_check"
    assert child.error is None
    assert store.load(world.root / CARD).stage == "implement"  # type: ignore[union-attr]
    again = type(sched)(client, world.root, check_timeout=20)  # the new server adopts the running turn
    try:
        assert at_rest(world, again, "shipped").error is None
    finally:
        again.close()


def test_a_tick_that_fails_fails_the_child_and_the_umbrella_asks_for_help(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    client.fail_tick = True
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
    finally:
        sched.close()
    assert "1 of 1 children need you" in str(st.error), dump(world)
    child = store.load(world.root / CARD / "children" / "umbr0001-1")
    assert child is not None
    assert child.extra["failed_stage"] == "shipping"


def test_an_umbrella_note_that_will_not_close_asks_for_help(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    client.fail_close = True
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "failed")
    finally:
        sched.close()
    assert "closing the umbrella note failed" in str(st.error)


def test_a_dead_gateway_goes_to_the_issue_log_and_the_child_is_not_free(world: Env, free: Free) -> None:
    free.up = False
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: fixed did it myself"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        st = at_rest(world, sched, "shipped")
    finally:
        sched.close()
    (row,) = issues.read(world.root / CARD)
    assert (row["child"], row["phase"]) == ("kuhyx/alpha", "start")
    assert "HTTP 503" in row["symptom"]
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["free"] is False
