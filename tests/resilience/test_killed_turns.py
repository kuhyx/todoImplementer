"""A turn killed by a signal (OOM, SIGKILL, reboot) or cut off by the network is retried, never escalated."""

from __future__ import annotations

from typing import Any

from runnerfakes import Env
from schedfakes import CARD as SINGLE
from schedfakes import IMPL, LIVE_OK, PLAN, state, wait, wait_stage
from schedfakes import boot as boot_single
from todoimpl.runner import retry

KILL = ({"_fake": "exit", "code": 247},)  # 128 + 119: a signal ended claude, no result event
OFFLINE = (
    {"_fake": "stderr", "text": "Error: getaddrinfo ENOTFOUND api.anthropic.com"},
    {"_fake": "exit", "code": 1},
)


def test_t1902_a_signal_killed_turn_rests_as_killed_then_resumes(world: Env) -> None:
    sched, _ = boot_single(world, PLAN, KILL, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(SINGLE)
        wait(lambda: state(world).stage == "paused_retry")
        st = state(world)
        assert (st.extra["retry_kind"], st.extra["kill_retries"]) == ("killed", 1)
        st = wait_stage(world, sched, "gate")
    finally:
        sched.close()
    assert "kill_retries" not in st.extra


def test_t1902_an_offline_turn_rests_as_network(world: Env) -> None:
    sched, _ = boot_single(world, PLAN, OFFLINE, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(SINGLE)
        wait(lambda: state(world).stage == "paused_retry")
        assert state(world).extra["retry_kind"] == "network"
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t1902_a_turn_killed_six_times_asks_kuhy_after_the_bound(world: Env) -> None:
    kills: list[tuple[dict[str, Any], ...]] = [KILL] * (retry.MAX_KILL_RETRIES + 1)
    sched, _ = boot_single(world, PLAN, *kills, done_check="true")
    try:
        sched.start(SINGLE)
        st = wait_stage(world, sched, "failed", turns=len(kills) + 1)
    finally:
        sched.close()
    assert st.error is not None
    assert st.error.startswith("The implement turn failed")
    assert len(world.calls()) == 1 + retry.MAX_KILL_RETRIES + 1


SLOW_KILL = ({"_fake": "sleep", "sec": 3.1}, *KILL)  # a loaded machine: each turn takes seconds, not tenths


def test_t1985_the_bound_is_reached_however_slow_each_turn_is(world: Env) -> None:
    # Seven turns in a row once shared one 20 s wait; under a busy gate run that wait ran out first.
    kills: list[tuple[dict[str, Any], ...]] = [SLOW_KILL] * (retry.MAX_KILL_RETRIES + 1)
    sched, _ = boot_single(world, PLAN, *kills, done_check="true")
    try:
        sched.start(SINGLE)
        st = wait_stage(world, sched, "failed", turns=len(kills) + 1)
    finally:
        sched.close()
    assert st.error is not None
    assert st.error.startswith("The implement turn failed")
