"""A turn has a wall-clock limit: the host kills a claude that outlives it and the run retries."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from launchfakes import STEM, invoke, rig
from runnerfakes import Env
from schedfakes import CARD, PLAN, boot, state, wait
from todoimpl.runner import claude, files, launch, orphans, turnhost

if TYPE_CHECKING:
    from pathlib import Path


def test_t1893_the_timeout_defaults_to_four_hours_and_is_configurable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(launch.TIMEOUT_VAR, raising=False)
    assert launch.turn_timeout() == 4 * 3600
    monkeypatch.setenv(launch.TIMEOUT_VAR, "90")
    assert launch.turn_timeout() == 90
    for bad in ("", "soon", "-5", "0"):
        monkeypatch.setenv(launch.TIMEOUT_VAR, bad)
        assert launch.turn_timeout() == 4 * 3600


def test_t1893_the_invocation_file_carries_the_timeout_to_the_host(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(launch.TIMEOUT_VAR, "77")
    _, inv = rig(world, tmp_path)
    assert launch._invocation(inv)  # json text
    assert '"timeout": 77' in launch._invocation(inv)


def test_t1893_the_host_kills_a_claude_past_its_deadline_and_says_why(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(launch.TIMEOUT_VAR, "0.3")
    run_dir, inv = rig(world, tmp_path)
    slow = claude.Invocation(("sh", "-c", "sleep 30"), inv.env, inv.cwd)
    orphans.begin(run_dir, STEM, "implement", None)
    invoke(run_dir, slow)
    started = time.monotonic()
    turnhost.run(run_dir, STEM, turnhost.Stop())
    assert time.monotonic() - started < 10
    done = files.read_json(run_dir / f"{STEM}.exit.json")
    assert done["code"] < 0  # killed by a signal
    assert done["timeout"] is True
    assert "exceeded" in (run_dir / f"{STEM}.stderr.log").read_text(encoding="utf-8")


def test_t1893_a_host_without_a_timeout_in_its_file_runs_unbounded(world: Env, tmp_path: Path) -> None:
    run_dir, inv = rig(world, tmp_path)
    orphans.begin(run_dir, STEM, "implement", None)
    invoke(run_dir, inv)  # an invocation file written by the previous server version has no timeout
    turnhost.run(run_dir, STEM, turnhost.Stop())
    assert "timeout" not in files.read_json(run_dir / f"{STEM}.exit.json")


def test_t1893_a_turn_that_outlives_the_limit_is_killed_and_the_run_retries(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(launch.TIMEOUT_VAR, "0.5")
    sched, _ = boot(world, ({"_fake": "sleep", "sec": 30},), PLAN, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "paused_retry")
        st = state(world)
        assert st.extra["resume_stage"] == "plan"
        assert "exceeded" in str(st.extra["retry_reason"])
    finally:
        sched.close()
