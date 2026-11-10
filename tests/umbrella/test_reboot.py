"""A reboot kills the manager's turn unit with no exit record: the round resumes that session, once."""

from __future__ import annotations

import json
from typing import Any

from runnerfakes import Env
from test_restart_ship import _seed
from tierfakes import Free
from todoimpl.board import state as store
from todoimpl.runner import orphans
from todoimpl.runner.scheduler import Scheduler
from todoimpl.umbrella.store import child_dir
from umbrellarig import CARD, LIVE, NOTE, at_rest, boot, manager, script_live

STEM = "manager-1.000"


def _lost_manager_turn(world: Env, session: str) -> None:
    """Leave what a reboot leaves in the run dir: a half-written stream, a record, a dead host."""
    run_dir = world.root / CARD
    run_dir.mkdir(parents=True, exist_ok=True)
    init = {"type": "system", "subtype": "init", "session_id": session}
    (run_dir / f"{STEM}.stream.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    orphans.begin(run_dir, STEM, "manager", None)
    orphans.write(run_dir, launched=1.0, host_pid=2_000_000_000, host_start="1")  # a pid no process has


def _interrupted_round(world: Env, client: Any) -> None:
    record: dict[str, Any] = {"width": 1, "tier": None, "kids": [], "rounds": [], "current": None}
    st = store.RunState(task_id=CARD, stage="implement", extra={"umbrella": record})
    st.sessions["manager"] = {"session_id": "mgr-sess", "last_turn_end": 0.0, "route": "plan"}
    store.save(world.root / CARD, st)
    _lost_manager_turn(world, "mgr-sess")


def test_t1907_a_manager_turn_lost_to_a_reboot_resumes_its_session_and_starts_no_child_twice(
    world: Env, free: Free
) -> None:
    sched, client = boot(world, 1)
    sched.close()
    _interrupted_round(world, client)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    again = Scheduler(client, world.root, check_timeout=20)  # the board unit came back after the boot
    try:
        st = at_rest(world, again, "gate")
    finally:
        again.close()
    managers = [
        c for c in world.calls() if "Umbrella manager" in str(c["prompt"]) or "killed" in str(c["prompt"])
    ]
    assert len(managers) == 1
    assert managers[0]["resume"] == "mgr-sess"
    assert "killed mid-work" in managers[0]["prompt"]
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["ok"] is True
    children = [c for c in world.calls() if str(c["cwd"]).endswith("wt")]
    assert len(children) == 1  # the child's live check ran once


def test_a_child_turn_lost_to_a_reboot_resumes_its_session_once(world: Env, free: Free) -> None:
    sched, client = boot(world, 1)
    sched.close()
    cid = _seed(world, client, "live_check")
    cdir = child_dir(world.root / CARD, cid)
    child = store.load(cdir)
    assert child is not None
    child.sessions["implement"] = {"session_id": "kid-sess", "last_turn_end": 0.0, "route": "plan"}
    child.worktree = None  # re-attached by the drive
    store.save(cdir, child)
    stem = "implement-1.000"
    init = {"type": "system", "subtype": "init", "session_id": "kid-sess"}
    (cdir / f"{stem}.stream.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    orphans.begin(cdir, stem, "implement", None)
    orphans.write(cdir, launched=1.0, host_pid=2_000_000_000, host_start="1")
    world.script(cid, *LIVE)
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        at_rest(world, again, "gate")
    finally:
        again.close()
    calls = [c for c in world.calls() if str(c["cwd"]).endswith("wt")]
    assert len(calls) == 1
    assert calls[0]["resume"] == "kid-sess"
    assert "killed mid-work" in calls[0]["prompt"]
