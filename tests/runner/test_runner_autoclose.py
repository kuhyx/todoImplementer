"""Auto-close end to end: a trusted done_check that turns green starts a `closing` run without a click."""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING

import pytest
from autofakes import arm, poller
from contract_lib import validate
from runnerfakes import Env, FakeClient, make_repo, sh, task
from schedfakes import CARD, reply, state, wait_stage
from todoimpl.board import state as store
from todoimpl.runner.autocheck import STARTED, WAITING, load_cache
from todoimpl.runner.scheduler import RunnerError, Scheduler

if TYPE_CHECKING:
    from pathlib import Path


def _world(world: Env, *turns: tuple[dict[str, object], ...]) -> tuple[Scheduler, FakeClient, Path]:
    repo = make_repo(world)
    marker = world.tmp / "marker"
    check = f"test -e {marker}"
    client = FakeClient({"abcd1234": task(done_check=check)})
    arm(world, check)
    for turn in turns:
        world.script("demo", *turn)
    assert repo.is_dir()
    return Scheduler(client, world.root, check_timeout=20), client, marker


def test_marker_appearing_starts_a_closing_run_without_a_click(world: Env) -> None:
    sched, client, marker = _world(world, reply("C1: the marker exists, check passes\n\nD: confirmed"))
    auto = poller(world, sched, client)
    try:
        auto.tick()
        assert store.load(world.root / CARD) is None
        marker.touch()
        auto.tick()
        st = wait_stage(world, sched, "gate", tag="D")
        validate("state", st.to_dict())
        assert st.auto_start is not None
        assert st.auto_start["reason"] == "done_check"
        assert st.worktree is None
        assert not (world.root / CARD / "wt").exists()
        call = world.calls()[0]
        assert call["model"] == "opus"  # T2471
        assert call["cwd"] == str(world.src / "demo")
        assert "Edit" in call["argv"]
        assert st.checks is not None
        assert st.checks["passed"]
        assert sh(world.src / "demo", "git", "status", "--porcelain") == ""
        cache = json.loads((world.root / "autocheck.json").read_text(encoding="utf-8"))
        assert cache[CARD]["passed"] is True
    finally:
        sched.close()


CONFIRM = reply("C1: marker exists\n\nD: confirmed")


def test_close_with_the_check_green_closes_the_item_and_keeps_the_badge(world: Env) -> None:
    sched, client, marker = _world(world, CONFIRM)
    marker.touch()
    try:
        assert sched.auto_start(CARD, 123.0)
        assert not sched.auto_start(CARD, 124.0)
        wait_stage(world, sched, "gate", tag="D")
        with pytest.raises(RunnerError, match="only at the gate"):
            sched.ship(CARD)
        sched.close_item(CARD)
        st = state(world)
        assert (st.stage, st.auto_start) == ("closed", {"reason": "done_check", "passed_at": 123.0})
        assert client.closed[0][0] == CARD
        assert f"done_check `test -e {marker}` exit 0" in client.closed[0][1]
        assert "Closing turn: C1: marker exists" in client.closed[0][1]
        with pytest.raises(RunnerError, match="already closed"):
            sched.cancel(CARD)
        with pytest.raises(RunnerError, match="only at the gate"):
            sched.close_item(CARD)
    finally:
        sched.close()


def test_close_with_the_check_red_fails_and_leaves_the_item_open(world: Env) -> None:
    sched, client, marker = _world(world, CONFIRM)
    marker.touch()
    try:
        sched.auto_start(CARD, 1.0)
        wait_stage(world, sched, "gate", tag="D")
        marker.unlink()
        sched.close_item(CARD)
        st = state(world)
        assert st.stage == "failed"
        assert st.error == "The done_check is red at Close (exit 1): the item stays open"
        assert client.closed == []
    finally:
        sched.close()


def test_close_that_the_todo_app_refuses_fails_with_its_reason(world: Env) -> None:
    sched, client, marker = _world(world, CONFIRM)
    marker.touch()
    client.fail_close = True
    try:
        sched.auto_start(CARD, 1.0)
        wait_stage(world, sched, "gate", tag="D")
        sched.close_item(CARD)
        assert state(world).error == "Closing the item failed: close refused"
    finally:
        sched.close()


def test_red_recheck_after_the_turn_fails_then_only_a_start_with_a_pass_reruns(world: Env) -> None:
    sched, client, marker = _world(world, CONFIRM, CONFIRM)
    auto = poller(world, sched, client)
    try:
        sched.auto_start(CARD, 1.0)
        st = wait_stage(world, sched, "failed")
        assert st.error == "The done_check is red again (exit 1): nothing was closed"
        with pytest.raises(RunnerError, match="closing runs take no notes"):
            sched.send(CARD, "please")
        marker.touch()
        auto.tick()
        assert state(world).stage == "failed"
        sched.start(CARD)
        st = wait_stage(world, sched, "gate", tag="D")
        assert st.error is None
        assert len(world.calls()) == 2
    finally:
        sched.close()


def test_start_that_loses_to_the_auto_start_does_nothing_and_vice_versa(world: Env) -> None:
    sched, _client, marker = _world(world, CONFIRM)
    marker.touch()
    try:
        with sched._cv:  # hold the lock: the auto-start is queued, not yet driving
            assert sched.auto_start(CARD, 1.0)
            sched.start(CARD)
        assert state(world).stage == "closing"
        wait_stage(world, sched, "gate", tag="D")
    finally:
        sched.close()


def test_a_click_landing_mid_poll_wins_and_the_poll_starts_nothing(world: Env) -> None:
    sched, client, marker = _world(world)
    slow = f"sleep 0.4; test -e {marker}"
    client.tasks["abcd1234"] = task(done_check=slow)
    arm(world, slow)
    marker.touch()
    auto = poller(world, sched, client)
    ticking = threading.Thread(target=auto.tick)
    try:
        ticking.start()
        sched.start(CARD)
        ticking.join()
        assert state(world).auto_start is None
        cache = json.loads((world.root / "autocheck.json").read_text(encoding="utf-8"))
        assert CARD not in cache or cache[CARD]["reason"] == "passes, a run already exists"
    finally:
        sched.close()


def test_auto_start_refuses_unknown_items_corrupt_state_and_busy_cards(world: Env) -> None:
    sched, _client, _ = _world(world)
    try:
        assert not sched.auto_start("ffff0000-0", 1.0)
        (world.root / CARD).mkdir(parents=True)
        (world.root / CARD / "state.json").write_text("{", encoding="utf-8")
        assert not sched.auto_start(CARD, 1.0)
        (world.root / CARD / "state.json").unlink()
        with sched._cv:
            sched.enqueue(CARD)
            assert not sched.auto_start(CARD, 1.0)
            sched._queue.clear()
    finally:
        sched.close()


def test_a_closing_run_whose_item_lost_its_check_fails(world: Env) -> None:
    sched, client, _ = _world(world)
    client.tasks["abcd1234"] = task(done_check=None)
    try:
        assert sched.auto_start(CARD, 1.0)
        st = wait_stage(world, sched, "failed")
        assert st.error == "The item no longer has a done_check: a closing run needs one"
    finally:
        sched.close()


def test_t903_a_red_server_rerun_marks_the_poll_entry_red_at_once(world: Env) -> None:
    sched, _client, marker = _world(world, CONFIRM, CONFIRM)
    passed = {"at": 1.0, "passed": True, "trusted": True, "reason": STARTED, "pending": False}
    (world.root / "autocheck.json").write_text(json.dumps({CARD: passed}), encoding="utf-8")
    try:
        sched.auto_start(CARD, 1.0)
        wait_stage(world, sched, "failed")
        assert load_cache(world.root)[CARD]["passed"] is False
        assert load_cache(world.root)[CARD]["reason"] == WAITING
        (world.root / "autocheck.json").write_text(json.dumps({CARD: passed}), encoding="utf-8")
        marker.touch()
        sched.start(CARD)
        wait_stage(world, sched, "gate", tag="D")
        marker.unlink()
        sched.close_item(CARD)
        assert load_cache(world.root)[CARD]["passed"] is False
    finally:
        sched.close()
