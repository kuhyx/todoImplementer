"""Credit turns end to end: the fake SDK plays the fake claude under the real turn host and scheduler."""

import time
from collections.abc import Callable
from datetime import date

import pytest
from creditfakes import enable_credits, reach_cap
from phonefakes import READY, SERIAL, fake_adb, phone_turn
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, lift_limit, reply, state, wait, wait_stage
from todoimpl.apikey import cache
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.credits import marks, setting
from todoimpl.runner import limits
from todoimpl.runner.phone_sched import PhoneWatcher


def limit_on(world: Env) -> None:
    limits.write_until(world.root, time.time() + 3600)


def test_t1850_a_limited_run_goes_on_free_credits_and_back_on_the_plan(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-the-plan")
    limit_on(world)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert [c["via_sdk"] for c in calls] == [True, True, True]
        assert all(c["model"] == "sonnet" and c["api_key"] for c in calls)  # even implement: sonnet
        assert all(c["phone_owner"] == f"todoimpl:{CARD}" for c in calls)
        assert st.extra["route"] == "credits"
        assert {v["route"] for v in st.sessions.values()} == {"credits"}
    finally:
        sched.close()


def test_plan_turns_never_see_the_api_key(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    reach_cap(world.root)  # past the weekly cap the plan takes the turns
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-reach-the-plan")
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert not any(c["via_sdk"] or c["api_key"] for c in calls)
        assert calls[1]["model"] == "opus"
        assert st.extra["route"] == "plan"
    finally:
        sched.close()


def off(_world: Env, _mp: pytest.MonkeyPatch) -> None:
    setting.set_enabled(value=False)


def bad_key(_world: Env, _mp: pytest.MonkeyPatch) -> None:
    cache.put(KeyStatus("expired", date(2026, 11, 1), "expired on 2026-11-01"))


def no_sdk(_world: Env, mp: pytest.MonkeyPatch) -> None:
    mp.delenv("TODOIMPL_SDK_PYTHON")


def exhausted(world: Env, _mp: pytest.MonkeyPatch) -> None:
    marks.mark_exhausted(world.root, time.time() + 3600, "Credit balance is too low")


@pytest.mark.parametrize("hold", [off, bad_key, no_sdk, exhausted])
def test_t1850_fallback_is_only_chosen_when_every_condition_holds(
    world: Env, monkeypatch: pytest.MonkeyPatch, hold: Callable[[Env, pytest.MonkeyPatch], None]
) -> None:
    enable_credits(monkeypatch)
    limit_on(world)
    hold(world, monkeypatch)
    sched, _ = boot(world, PLAN, done_check="true")
    try:
        sched.start(CARD)
        time.sleep(0.8)  # the queue holds the card: the limit is active and the credits cannot take over
        assert world.calls() == []
        assert sched.running() == set()
        assert state(world).stage == "plan"
    finally:
        sched.close()


def test_t1852_credits_running_out_pauses_until_the_plan_resets_without_a_retry_loop(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    limit_on(world)
    out = reply("API Error: 400 Credit balance is too low", is_error=True)
    sched, _ = boot(world, out, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "paused_limit")
        assert st.error is None
        assert marks.exhausted(world.root, time.time())
        time.sleep(0.8)  # retry backoffs are 0.3 s in tests: a loop would have spent more turns
        assert len(world.calls()) == 1
        assert "retries" not in state(world).extra
        lift_limit(world, sched)
        st = wait_stage(world, sched, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [True, False, False, False]
        assert st.extra["route"] == "plan"
        assert marks.exhausted(world.root, time.time())  # kept to its end: no credit retry on every dispatch
    finally:
        sched.close()


def overage_turn(world: Env) -> tuple[dict[str, object], ...]:
    resets = time.time() + 3600
    return (
        {"_fake": "limit", "resets_at": resets, "status": "allowed", "using_overage": True},
        {"_fake": "sleep", "sec": 30},
    )


def test_t1853_overage_on_the_plan_kills_the_turn_alerts_and_pauses(world: Env) -> None:
    sched, _ = boot(world, overage_turn(world), PLAN, done_check="true")
    try:
        started = time.monotonic()
        sched.start(CARD)
        st = wait_stage(world, sched, "paused_limit")
        assert time.monotonic() - started < 15  # the sleep was 30 s: the guard stopped it live
        assert limits.active_until(world.root, time.time()) is not None
        alert = marks.active_alert(world.root, time.time())
        assert alert is not None
        assert "extra usage" in alert["text"]
        assert st.resume_at == alert["until"]
        assert len(world.calls()) == 1
    finally:
        sched.close()


def test_overage_on_the_plan_past_the_cap_pauses_instead_of_spending_credits(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    reach_cap(world.root)  # the plan runs the turns only because the credits are at their cap
    sched, _ = boot(world, overage_turn(world), PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "paused_limit")
        assert [c["via_sdk"] for c in world.calls()] == [False]
        assert marks.active_alert(world.root, time.time()) is not None
    finally:
        sched.close()


def test_t1854_phone_last_flow_works_for_a_credit_turn(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    limit_on(world)
    fake_adb(world)
    sched, _ = boot(world, PLAN, phone_turn(world), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        assert st.extra["waiting_phone"] == {**READY, "note": "plug in the Pixel"}
        assert st.extra["route"] == "credits"
        (world.tmp / "adb" / "devices").write_text(f"{SERIAL} device\n", encoding="utf-8")
        assert PhoneWatcher(sched).tick() is True
        st = wait_stage(world, sched, "gate")
        last = world.calls()[-1]
        assert last["via_sdk"] is True
        assert "The Pixel is attached now" in last["prompt"]
        assert "waiting_phone" not in st.extra
    finally:
        sched.close()


def test_a_turn_adopted_after_a_restart_keeps_its_route(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    limit_on(world)
    slow = ({"_fake": "sleep", "sec": 1.0}, *PLAN)
    sched, client = boot(world, slow, IMPL, LIVE_OK, done_check="true")
    sched.start(CARD)
    wait(lambda: len(world.calls()) == 1)
    sched.close()  # the credit turn keeps running under its host
    sched2 = type(sched)(client, world.root, check_timeout=20)
    try:
        wait_stage(world, sched2, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [True, True, True]
    finally:
        sched2.close()


def test_t1989_paced_credits_run_every_turn_with_no_limit_below_the_cap(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [True, True, True]
        assert st.extra["route"] == "credits"
        assert limits.active_until(world.root, time.time()) is None
    finally:
        sched.close()


def test_t1989_paced_credits_fall_back_to_the_plan_when_they_run_out(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    out = reply("API Error: 400 Credit balance is too low", is_error=True)
    sched, _ = boot(world, out, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [True, False, False, False]
        assert st.extra["route"] == "plan"
        assert marks.exhausted(world.root, time.time())  # kept: no credit retry on every dispatch
    finally:
        sched.close()


def test_t1989_the_cap_is_hard_a_limited_run_waits_instead_of_spending_past_it(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    reach_cap(world.root)
    limit_on(world)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        time.sleep(0.8)  # the plan is limited and the credits are past the cap: nothing starts
        assert world.calls() == []
        lift_limit(world, sched)
        st = wait_stage(world, sched, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [False, False, False]
        assert st.extra["route"] == "plan"
    finally:
        sched.close()
