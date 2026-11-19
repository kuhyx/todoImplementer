"""Every card ships itself at the gate, a closing run closes itself, a restart finishes both (T2060)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from autofakes import arm
from runnerfakes import Env, FakeClient, make_repo, sh, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.board.state import RunState
from todoimpl.runner.restart import restart_stage
from todoimpl.runner.scheduler import Scheduler
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

PLAIN = {"body": "done: hello.txt exists"}  # no done_check, no auto-ship tick


@pytest.fixture
def ships(monkeypatch: pytest.MonkeyPatch) -> None:
    """Apply the production rule: nothing rests at the gate (the suite holds it by default, see conftest)."""
    monkeypatch.delenv("TODOIMPL_HOLD_GATE")


def _log(world: Env) -> list[str]:
    return sh(world.tmp / "remotes" / "demo.git", "git", "log", "--format=%s", "main").splitlines()


def test_t2060_a_green_plain_card_ships_with_no_click_and_no_tick(world: Env, ships: None) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, **PLAIN)
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "shipped")
        assert not st.auto_ship
        assert _log(world) == ["Add hello file", "init"]
        assert len(client.closed) == 1
    finally:
        sched.close()


def test_t2060_a_card_resting_at_the_gate_when_the_server_starts_gets_shipped(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, **PLAIN)
    sched.start(CARD)
    wait_stage(world, sched, "gate")  # the hold: how a run rested before this rule
    sched.close()
    monkeypatch.delenv("TODOIMPL_HOLD_GATE")
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        wait_stage(world, again, "shipped")
        assert _log(world) == ["Add hello file", "init"]
        assert len(client.closed) == 1
    finally:
        again.close()


def test_t2060_a_failed_ship_retries_into_shipping_not_the_gate(ships: None) -> None:
    st = RunState(task_id=CARD, stage="failed", started_at=1.0)
    st.extra["failed_stage"], st.error = "shipping", "red after the rebase"
    item = Item("abcd1234", 0, "t", PLAIN["body"], "demo", "todo", None)
    assert restart_stage(st, item) == "shipping"


def _closing(world: Env) -> tuple[Scheduler, FakeClient, Path]:
    make_repo(world)
    marker = world.tmp / "marker"
    check = f"test -e {marker}"
    client = FakeClient({"abcd1234": task(done_check=check)})
    arm(world, check)
    world.script("demo", *reply("C1: marker exists\n\nD: confirmed"))
    marker.touch()
    return Scheduler(client, world.root, check_timeout=20), client, marker


def test_t2060_a_closing_run_closes_the_item_itself(world: Env, ships: None) -> None:
    sched, client, marker = _closing(world)
    try:
        assert sched.auto_start(CARD, 123.0)
        st = wait_stage(world, sched, "closed")
        assert st.auto_start == {"reason": "done_check", "passed_at": 123.0}
        assert client.closed[0][0] == CARD
        assert f"done_check `test -e {marker}` exit 0" in client.closed[0][1]
        assert "Closing turn: C1: marker exists" in client.closed[0][1]
    finally:
        sched.close()


def test_t2060_a_closing_run_resting_at_the_gate_closes_on_start(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, client, _ = _closing(world)
    sched.auto_start(CARD, 1.0)
    wait_stage(world, sched, "gate", tag="D")
    sched.close()
    monkeypatch.delenv("TODOIMPL_HOLD_GATE")
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        wait_stage(world, again, "closed")
        assert len(client.closed) == 1
        assert len(world.calls()) == 1  # the confirming turn is not paid for twice
    finally:
        again.close()


def test_t2060_a_red_recheck_does_not_close(world: Env, ships: None) -> None:
    sched, client, marker = _closing(world)
    marker.unlink()
    try:
        sched.auto_start(CARD, 1.0)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "red again" in st.error
        assert client.closed == []
    finally:
        sched.close()


def test_t2060_a_close_the_todo_app_refuses_fails_with_its_reason(world: Env, ships: None) -> None:
    sched, client, _ = _closing(world)
    client.fail_close = True
    try:
        sched.auto_start(CARD, 1.0)
        st = wait_stage(world, sched, "failed")
        assert st.error == "Closing the item failed: close refused"
    finally:
        sched.close()
