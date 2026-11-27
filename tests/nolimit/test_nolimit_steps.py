"""A no-limit step runs under capped.sh and `timeout`; past the limit it is cut and counts as slow."""

from __future__ import annotations

from runnerfakes import Env
from todoimpl.nolimit import steps


def test_t2542_a_step_past_the_limit_is_cut_and_slow(world: Env) -> None:
    cut = steps.run("gate", "echo started; sleep 30", world.tmp, limit=1)
    assert cut.slow
    assert not cut.passed
    assert cut.seconds < 10
    assert "started" in cut.tail


def test_a_step_keeps_its_exit_and_tail(world: Env) -> None:
    ok = steps.run("test", "seq 1 100", world.tmp)
    assert ok.passed
    assert ok.tail.splitlines()[0] == "61"  # the last 40 lines
    red = steps.run("test", "echo boom >&2; exit 3", world.tmp, env={"X": "1"})
    assert (red.exit_code, red.tail, red.slow) == (3, "boom", False)


def test_a_quick_124_is_a_red_step_not_a_cut(world: Env) -> None:
    assert steps.run("test", "exit 124", world.tmp).exit_code == 124


def test_a_failed_plumbing_step_is_red() -> None:
    step = steps.failed("git", "git fetch", "no network")
    assert (step.passed, step.slow, step.tail) == (False, False, "no network")


def test_t2618_a_step_runs_at_the_gate_steps_cap_and_a_caller_env_wins(world: Env) -> None:
    # live C10: kcd2's suite took 14.2 s at capped.sh's 10 % CPU and 9.4 s at 20 %, the board gate's own cap
    done = steps.run("cap", "echo $CAP_CPU_PCT $CAP_MEM $EXTRA", world.tmp, {"EXTRA": "x"})
    assert done.tail == "20 4G x"
    assert steps.run("cap", "echo $CAP_MEM", world.tmp, {"CAP_MEM": "2G"}).tail == "2G"
