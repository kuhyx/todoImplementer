"""A turn host that keeps dying (reboot loop, OOM killer) is waited out on the ladder, then asks kuhy."""

from __future__ import annotations

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait, wait_stage
from todoimpl.runner import pipeline, retry, turn
from todoimpl.runner.files import KilledError


def _dying(times: int) -> object:
    real = turn.run_turn
    left = {"n": times}

    def run_turn(*args: object, **kwargs: object) -> object:
        if left["n"] > 0:
            left["n"] -= 1
            msg = "The implement turn was lost 3 times: its host keeps dying; read the journal"
            raise KilledError(msg)
        return real(*args, **kwargs)  # type: ignore[arg-type]

    return run_turn


def test_t1902_a_host_that_died_three_times_rests_as_killed_and_the_stage_reruns(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "run_turn", _dying(2))  # the plan turn and the first implement turn
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "paused_retry")
        assert state(world).extra["retry_kind"] == "killed"
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t1902_a_host_that_never_stays_up_asks_kuhy_after_the_bound(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(pipeline, "run_turn", _dying(retry.MAX_KILL_RETRIES + 1))
    sched, _ = boot(world, PLAN, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
    finally:
        sched.close()
    assert st.error is not None
    assert "host keeps dying" in st.error
