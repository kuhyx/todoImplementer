"""A turn that sent its result and then sat idle (a background-task notice) is ended, not waited on."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from adoptfakes import env, go, rig
from runnerfakes import Env
from todoimpl.board.state import RunState
from todoimpl.runner import adopt, idle, orphans
from todoimpl.runner.turn import run_turn


def test_t1991_a_turn_idle_after_its_result_is_ended_and_returns_the_result(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 0.5)
    world.script(
        "abcd1234",
        {"_fake": "result", "text": "Build running.\n\nR: waiting for the build"},
        {"_fake": "sleep", "sec": 60},  # claude -p stays alive for a background-task notice
    )
    started = time.monotonic()
    res = run_turn(env(run_dir, wt, []), RunState(task_id="abcd1234-0", stage="implement"), "implement", go)
    assert time.monotonic() - started < 20
    assert res.tag == "R"
    assert res.finished
    assert orphans.read(run_dir) is None


def test_t1991_a_turn_still_silent_before_its_result_is_not_ended(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 0.2)
    world.script(
        "abcd1234",
        {"_fake": "sleep", "sec": 1.5},  # a long thinking pause is no idle session: no result yet
        {"_fake": "result", "text": "D: ok"},
    )
    res = run_turn(env(run_dir, wt, []), RunState(task_id="abcd1234-0", stage="implement"), "implement", go)
    assert res.tag == "D"


def test_t1991_a_running_shell_below_claude_counts_as_a_build_in_progress(tmp_path: Path) -> None:
    assert idle._read(tmp_path / "gone") == ""
    assert not idle.shell_running(None)
    assert not idle.shell_running(2**22 + 12345)  # no such process
    # `; :` keeps bash alive: a lone command is exec-replaced and no shell is left
    shell = subprocess.Popen(["bash", "-c", "sleep 5; :"])
    try:
        deadline = time.monotonic() + 5
        while not idle.shell_running(os.getpid()) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert idle.shell_running(os.getpid())
        assert not idle.Clock(0.0).due(finished=True, now=99, limit=1, claude_pid=os.getpid())
    finally:
        shell.kill()
        shell.wait()
    nested = subprocess.Popen(["bash", "-c", "sleep 5; :"])  # a shell whose child is no shell
    try:
        deadline = time.monotonic() + 5
        while not idle._children(nested.pid) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert not idle.shell_running(nested.pid)
    finally:
        nested.kill()
        nested.wait()
    assert idle.Clock(0.0).due(finished=True, now=99, limit=1, claude_pid=None)
    assert not idle.Clock(0.0).due(finished=False, now=99, limit=1, claude_pid=None)
    assert not idle.Clock(0.0).due(finished=True, now=0, limit=1, claude_pid=None)


def test_t2194_a_turn_whose_background_job_just_ended_gets_to_answer_its_notice(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 1.0)
    monkeypatch.setattr(idle, "LOOK_EVERY", 0.05)
    monkeypatch.setattr(idle, "SHELL_GRACE", 1.0)
    world.script(
        "abcd1234",
        {"_fake": "result", "text": "Build running.\n\nR: waiting for the build"},
        {"_fake": "shell", "sec": 2.0},  # the background job outlives the idle limit, counted from the result
        {"_fake": "sleep", "sec": 0.2},  # claude takes the job's notice and answers
        {"_fake": "result", "text": "Built.\n\nD: done"},
    )
    res = run_turn(env(run_dir, wt, []), RunState(task_id="abcd1234-0", stage="implement"), "implement", go)
    assert res.tag == "D"  # not stopped the moment the job's shell left


def test_t2194_the_idle_clock_starts_when_the_last_job_ends_not_at_the_result(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 1.0)
    monkeypatch.setattr(idle, "LOOK_EVERY", 0.05)
    monkeypatch.setattr(idle, "SHELL_GRACE", 1.0)
    world.script(
        "abcd1234",
        {"_fake": "result", "text": "R: waiting for the build"},
        {"_fake": "shell", "sec": 2.0},
        {"_fake": "sleep", "sec": 60},  # the notice never reaches claude (T1991)
    )
    started = time.monotonic()
    res = run_turn(env(run_dir, wt, []), RunState(task_id="abcd1234-0", stage="implement"), "implement", go)
    took = time.monotonic() - started
    assert res.tag == "R"
    assert 2.8 < took < 20  # the job's 2 s plus the 1 s grace, not 1 s after the result


def test_t2194_a_shell_seen_resets_the_clock_and_a_quiet_turn_falls_due(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    alive = [True]
    monkeypatch.setattr(idle, "shell_running", lambda _pid: alive[0])
    clock = idle.Clock(0.0)
    assert not clock.due(finished=False, now=100.0, limit=10, claude_pid=1)  # no result yet: never due
    assert not clock.due(finished=True, now=100.0, limit=10, claude_pid=1)  # a live shell: busy now
    alive[0] = False
    assert not clock.due(finished=True, now=100.5, limit=10, claude_pid=1)  # no new look within LOOK_EVERY
    assert not clock.due(finished=True, now=159.0, limit=10, claude_pid=1)  # the shell left 59 s ago
    assert clock.due(finished=True, now=160.0, limit=10, claude_pid=1)
    clock.heard(200.0)  # the stream spoke
    assert not clock.due(finished=True, now=205.0, limit=10, claude_pid=1)
    assert clock.due(finished=True, now=210.0, limit=10, claude_pid=1)  # silent 10 s, no shell for 110 s
