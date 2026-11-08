"""Consuming turns: exactly-once bookkeeping, foreign roles, lost hosts, recovery, close and cancel."""

from __future__ import annotations

import os
import signal
import time
from pathlib import Path
from typing import Any

import pytest
from adoptfakes import STEM, Crash, env, finished_turn, go, kinds, result, rig
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, PLAN, state, wait
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import adopt, claude, files, launch, orphans
from todoimpl.runner.scheduler import Scheduler
from todoimpl.runner.turn import run_turn


def test_t1817_a_crash_between_result_json_and_the_state_save_costs_nothing_twice(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    world.script(
        "abcd1234", {"_fake": "text", "text": "hi"}, {"_fake": "result", "text": "D: ok", "cost": 0.5}
    )
    events: list[dict[str, Any]] = []
    with monkeypatch.context() as patch:
        patch.setattr(store, "save", lambda *_a: (_ for _ in ()).throw(Crash()))
        with pytest.raises(Crash):
            run_turn(
                env(run_dir, wt, events), RunState(task_id="abcd1234-0", stage="implement"), "implement", go
            )
    assert len(list(run_dir.glob("*.result.json"))) == 1  # result.json written, the state save never happened
    assert store.load(run_dir) is None
    # the restart: the state on disk knows nothing of the turn, the record and exit record are still there
    fresh = RunState(task_id="abcd1234-0", stage="implement")
    res = run_turn(env(run_dir, wt, events), fresh, "implement", go)
    assert res.tag == "D"
    assert fresh.cost_usd == 0.5
    assert len(world.calls()) == 1  # the finished turn was adopted, not rerun
    assert orphans.read(run_dir) is None
    on_disk = store.load(run_dir)
    assert on_disk is not None
    assert on_disk.cost_usd == 0.5
    assert on_disk.extra["consumed_turn"].startswith("implement-")


def test_t1817_a_crash_after_the_state_save_replays_the_stream_without_charging_again(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    # No session id: the per-session cost ledger cannot absorb a second application, only the marker can.
    world.script("abcd1234", {"_fake": "bare"}, {"_fake": "result", "text": "D: ok", "cost": 0.5})
    events: list[dict[str, Any]] = []
    with monkeypatch.context() as patch:
        patch.setattr(orphans, "clear", lambda *_a: (_ for _ in ()).throw(Crash()))
        with pytest.raises(Crash):
            run_turn(
                env(run_dir, wt, events), RunState(task_id="abcd1234-0", stage="implement"), "implement", go
            )
    saved = store.load(run_dir)
    assert saved is not None
    assert saved.cost_usd == 0.5
    res = run_turn(env(run_dir, wt, events), saved, "implement", go)
    assert res.tag == "D"
    assert saved.cost_usd == 0.5
    assert len(world.calls()) == 1
    assert orphans.read(run_dir) is None


def test_a_finished_turn_of_another_role_is_charged_and_dropped_then_the_asked_turn_runs(
    world: Env, tmp_path: Path
) -> None:
    run_dir, wt = rig(world, tmp_path)
    finished_turn(run_dir, "plan-1.000", "plan", result("D: planned", cost=0.25))
    st = RunState(task_id="abcd1234-0", stage="implement")
    res = run_turn(env(run_dir, wt, []), st, "implement", go)
    assert res.text == "Did the thing.\n\nD: done"  # the implement turn's own result, not the plan's
    assert st.cost_usd == 0.26  # the plan turn's 0.25 was kept, then the implement turn's 0.01
    assert st.sessions["plan"]["session_id"] == "s1"
    assert [c["model"] for c in world.calls()] == ["opus"]


def test_turns_that_keep_getting_lost_stop_the_run_for_kuhy(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(launch, "host_argv", lambda *_a: ["true"])  # a host that records nothing
    monkeypatch.setattr(adopt, "START_GRACE", 0.0)
    events: list[dict[str, Any]] = []
    with pytest.raises(files.NeedsYouError, match="lost 3 times"):
        run_turn(env(run_dir, wt, events), RunState(task_id="abcd1234-0", stage="implement"), "implement", go)
    assert sum("turn lost" in text for _, text in kinds(events)) == 3


def test_recover_queues_a_run_waiting_on_kuhy_when_a_finished_turn_is_still_unconsumed(world: Env) -> None:
    make_repo(world)
    run_dir = world.root / CARD
    finished_turn(run_dir, STEM, "implement", result("Q: which name?"))
    store.save(run_dir, RunState(task_id=CARD, stage="implement", last_tag="Q"))  # stale: the tag is old
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        wait(lambda: state(world).extra.get("consumed_turn") == STEM and CARD not in sched.running())
    finally:
        sched.close()
    assert state(world).last_tag == "Q"
    assert world.calls() == []  # adopted from the exit record: no claude was started


def test_closing_the_server_lets_go_of_a_running_turn_without_signalling_it(world: Env) -> None:
    make_repo(world)
    world.script("abcd1234", *PLAN)
    world.script("abcd1234", {"_fake": "text", "text": "busy"}, {"_fake": "sleep", "sec": 60})
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    sched.start(CARD)
    run_dir = world.root / CARD

    def implementing() -> bool:
        rec = orphans.read(run_dir)
        return rec is not None and rec.role == "implement" and rec.pid is not None and len(world.calls()) == 2

    wait(implementing)
    rec = orphans.read(run_dir)
    assert rec is not None
    begun = time.monotonic()
    sched.close()
    assert time.monotonic() - begun < 5  # drives detach at once instead of joining a 60 s turn
    assert orphans.alive(rec.pid, rec.start)
    os.killpg(rec.pid or 0, signal.SIGKILL)


def test_cancelling_a_run_nobody_drives_stops_its_leftover_turn(world: Env) -> None:
    make_repo(world)
    run_dir = world.root / CARD
    wt = world.tmp / "abcd1234-demo"
    wt.mkdir()
    world.script("abcd1234", {"_fake": "sleep", "sec": 30})
    store.save(run_dir, RunState(task_id=CARD, stage="failed"))
    launch.start(run_dir, STEM, "implement", claude.build("implement", "go", wt))
    wait(lambda: (orphans.read(run_dir) or orphans.Record()).pid is not None)
    live = orphans.read(run_dir)
    assert live is not None
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        sched.cancel(CARD)
    finally:
        sched.close()
    assert state(world).stage == "cancelled"
    wait(lambda: not orphans.alive(live.pid, live.start))
