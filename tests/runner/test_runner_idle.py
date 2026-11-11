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
    shell = subprocess.Popen(["bash", "-c", "sleep 5"])
    try:
        deadline = time.monotonic() + 5
        while not idle.shell_running(os.getpid()) and time.monotonic() < deadline:
            time.sleep(0.05)
        assert idle.shell_running(os.getpid())
        assert not idle.should_stop(finished=True, silent_for=99, limit=1, claude_pid=os.getpid())
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
    assert idle.should_stop(finished=True, silent_for=99, limit=1, claude_pid=None)
    assert not idle.should_stop(finished=False, silent_for=99, limit=1, claude_pid=None)
    assert not idle.should_stop(finished=True, silent_for=0, limit=1, claude_pid=None)
