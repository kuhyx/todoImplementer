"""T1817: a restart of the server never touches a running claude turn; the new server adopts it."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
from pathlib import Path
from typing import Any

import todoimpl
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, state, wait, wait_stage
from todoimpl.runner import files, orphans
from todoimpl.runner.scheduler import Scheduler

HERE = Path(__file__).resolve().parent
SERVER_PATH = str(Path(todoimpl.__file__).resolve().parents[1])


def _slow_impl(sec: float) -> tuple[dict[str, Any], ...]:
    return ({"_fake": "text", "text": "working on it"}, {"_fake": "sleep", "sec": sec}, *IMPL)


def _server(world: Env) -> subprocess.Popen[bytes]:
    env = {**os.environ, "PYTHONPATH": SERVER_PATH}
    return subprocess.Popen([sys.executable, str(HERE / "detach_server.py"), CARD], env=env)


def _record(world: Env) -> orphans.Record:
    """Wait until the implement turn has started writing its stream."""
    run_dir = world.root / CARD

    def ready() -> bool:
        rec = orphans.read(run_dir)
        stream = run_dir / f"{rec.stem}.stream.jsonl" if rec else None
        return (
            rec is not None and rec.role == "implement" and stream is not None and stream.stat().st_size > 0
        )

    wait(ready)
    rec = orphans.read(run_dir)
    assert rec is not None
    return rec


def _gone(pid: int) -> bool:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
    except OSError:
        return True
    return stat.rpartition(")")[2].split()[0] == "Z"


def _crash_server(world: Env, *turns: tuple[dict[str, Any], ...]) -> orphans.Record:
    """Boot the server stand-in, let the implement turn start, SIGKILL the server; return the turn record."""
    make_repo(world)
    for turn in turns:
        world.script("abcd1234", *turn)
    server = _server(world)
    try:
        rec = _record(world)
    finally:
        server.kill()
        server.wait()
    return rec


def _second_server(world: Env) -> Scheduler:
    return Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)


def _events(world: Env) -> list[dict[str, Any]]:
    path = world.root / CARD / "events.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _exit(world: Env, rec: orphans.Record) -> dict[str, Any]:
    data = files.read_json(world.root / CARD / f"{rec.stem}.exit.json")
    assert isinstance(data, dict)
    return data


def test_t1817_a_running_turn_survives_a_server_kill_and_is_adopted(world: Env) -> None:
    rec = _crash_server(world, PLAN, _slow_impl(2.0), LIVE_OK)
    assert rec.pid is not None
    assert not _gone(rec.pid)  # the turn outlived the SIGKILLed server
    sched = _second_server(world)
    try:
        st = wait_stage(world, sched, "gate")
    finally:
        sched.close()
    assert len(world.calls()) == 3  # plan, implement, live check: the implement turn was not rerun
    assert "resume" not in world.calls()[1] or world.calls()[1]["resume"] is None
    assert _exit(world, rec)["code"] == 0  # same claude, never signalled
    assert _exit(world, rec)["pid"] == rec.pid
    assert st.cost_usd == 0.03  # plan, implement and the live check (its own session now) 0.01 each
    texts = [e["text"] for e in _events(world) if e["kind"] == "text" and e["text"] == "working on it"]
    assert texts == ["working on it"]  # replayed without publishing the feed twice
    assert orphans.read(world.root / CARD) is None


def test_t1817_a_turn_that_ended_while_no_server_ran_is_picked_up_from_exit_json(world: Env) -> None:
    rec = _crash_server(world, PLAN, _slow_impl(0.5), LIVE_OK)
    exit_json = world.root / CARD / f"{rec.stem}.exit.json"
    wait(exit_json.exists)
    sched = _second_server(world)
    try:
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
    assert len(world.calls()) == 3
    assert state(world).cost_usd == 0.03


def test_t1817_a_lost_turn_shows_an_error_and_resumes_the_killed_session(world: Env) -> None:
    rec = _crash_server(world, PLAN, _slow_impl(30), IMPL, LIVE_OK)
    assert rec.pid is not None
    assert rec.host_pid is not None
    os.kill(rec.host_pid, signal.SIGKILL)
    os.killpg(rec.pid, signal.SIGKILL)
    wait(lambda: _gone(rec.host_pid or 0) and _gone(rec.pid or 0))
    sched = _second_server(world)
    try:
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
    lost = [e for e in _events(world) if e["kind"] == "error" and "turn lost" in e["text"]]
    assert lost
    assert world.calls()[2]["resume"]  # the killed implement session was resumed
    assert not (world.root / CARD / f"{rec.stem}.exit.json").exists()


def test_t1817_cancel_stops_an_adopted_turn(world: Env) -> None:
    rec = _crash_server(world, PLAN, _slow_impl(60))
    assert rec.pid is not None
    sched = _second_server(world)
    try:
        wait(lambda: CARD in sched.running())
        sched.cancel(CARD)
        wait_stage(world, sched, "cancelled")
    finally:
        sched.close()
    wait(lambda: _gone(rec.pid or 0))
    assert _exit(world, rec)["code"] != 0
