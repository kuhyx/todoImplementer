"""The context cap end to end: a board session over TODOIMPL_CTX_CAP is cut and its role goes on fresh."""

import json
import time

import pytest
from contract_lib import validate
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, PLAN_TEXT, boot, wait_stage
from todoimpl.runner import retry


def assistant(tokens: int, *, parent: str | None = None) -> dict[str, object]:
    """Return a raw assistant event whose context is `tokens`, split over the three input kinds."""
    tenth = tokens // 10
    usage = {
        "input_tokens": tenth,
        "cache_creation_input_tokens": tenth,
        "cache_read_input_tokens": tokens - 2 * tenth,
        "output_tokens": 50,
    }
    event: dict[str, object] = {
        "type": "assistant",
        "message": {"id": f"msg_{tokens}", "usage": usage, "content": []},
    }
    if parent is not None:
        event["parent_tool_use_id"] = parent
    return event


def raw(event: dict[str, object]) -> dict[str, str]:
    return {"_fake": "raw", "text": json.dumps(event)}


HOLD = (raw(assistant(350_000)), {"_fake": "sleep", "sec": 30})  # over the 300000 default, then silence
SMALL_PLAN = (raw(assistant(40_000)), {"_fake": "result", "text": PLAN_TEXT})


def test_t2363_a_plan_turn_over_the_cap_is_cut_and_the_role_goes_on_in_a_fresh_seeded_session(
    world: Env,
) -> None:
    sched, _ = boot(world, HOLD, SMALL_PLAN, IMPL, LIVE_OK, done_check="true")
    began = time.monotonic()
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert time.monotonic() - began < 25  # the first turn would have slept 30 s: it was cut, not awaited
        calls = world.calls()
        assert len(calls) == 4
        assert calls[1]["resume"] is None  # a new session, not the over-cap one
        assert "stopped at the context cap" in calls[1]["prompt"]
        assert "git status" in calls[1]["prompt"]
        assert "git log" in calls[1]["prompt"]
        assert st.assignee == "claude"  # the card carried on by itself: never in "needs you"
        assert st.error is None
    finally:
        sched.close()


def test_t2364_the_credit_route_is_cut_at_the_cap_too(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    sched, _ = boot(world, HOLD, SMALL_PLAN, IMPL, LIVE_OK, done_check="true")
    began = time.monotonic()
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert time.monotonic() - began < 25
        calls = world.calls()
        assert [c["via_sdk"] for c in calls] == [True] * 4  # the same events, read by the credit guard
        assert calls[1]["resume"] is None
        assert "stopped at the context cap" in calls[1]["prompt"]
        assert st.extra["ctx_reseeds"] == {"plan": 1}
    finally:
        sched.close()


def test_t2365_a_session_already_over_the_cap_is_cut_on_its_first_event_and_subagents_do_not_count(
    world: Env,
) -> None:
    tell = {"_fake": "result", "text": "still going\n\nR: more to do"}
    sub = raw(assistant(900_000, parent="toolu_sub"))  # a subagent is not counted
    first = (sub, raw(assistant(100_000)), tell)
    sched, _ = boot(world, PLAN, first, HOLD, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate", turns=3)
        calls = world.calls()
        assert len(calls) == 5  # turn 2 ran to its tag, turn 3 was cut on its first event, turn 4 is fresh
        assert calls[2]["resume"]  # the running session carried on, as before the cap
        assert calls[3]["resume"] is None
    finally:
        sched.close()


def test_t2366_a_cap_stop_is_no_crash_no_kill_and_adds_no_backoff(world: Env) -> None:
    sched, _ = boot(world, HOLD, HOLD, HOLD, HOLD, SMALL_PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate", turns=5)
        assert len(world.calls()) == 7  # four stops, more than MAX_CRASH_RETRIES and MAX_KILL_RETRIES allow
        assert retry.MAX_CRASH_RETRIES < 4
        for key in ("retries", "crash_retries", "kill_retries", "retry_reason", "resume_at"):
            assert key not in st.extra
        assert st.resume_at is None
        assert st.extra["ctx_reseeds"] == {"plan": 4}
    finally:
        sched.close()


def test_t2366_the_seed_keeps_the_roles_last_reply(world: Env) -> None:
    said = {"_fake": "result", "text": "Half the work is in hello.txt\n\nR: continue"}
    sched, _ = boot(world, PLAN, (said,), HOLD, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate", turns=3)
        # the cut turn had no reply of its own: the one before it is still in the handoff summary
        assert "Half the work is in hello.txt" in world.calls()[3]["prompt"]
    finally:
        sched.close()


def test_t2367_state_records_the_context_per_session_and_the_reseed_count(world: Env) -> None:
    sched, _ = boot(world, HOLD, SMALL_PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert st.sessions["plan"]["context_tokens"] == 40_000  # the fresh session's last main-thread context
        assert st.extra["ctx_reseeds"] == {"plan": 1}
        assert "ctx_fresh" not in st.extra  # the seed marker ends when the fresh turn finishes
        assert "ctx_hit" not in st.extra
        validate("state", json.loads((world.root / CARD / "state.json").read_text(encoding="utf-8")))
        result = next((world.root / CARD).glob("plan-*.result.json"))
        assert json.loads(result.read_text(encoding="utf-8"))["context_tokens"] in (40_000, 350_000)
    finally:
        sched.close()


def test_t2368_cap_zero_turns_the_cap_off(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_CTX_CAP", "0")
    over = (raw(assistant(1_200_000)), {"_fake": "result", "text": PLAN_TEXT})
    sched, _ = boot(world, over, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert len(world.calls()) == 3
        assert "ctx_reseeds" not in st.extra
        assert st.sessions["plan"]["context_tokens"] == 1_200_000  # still metered
    finally:
        sched.close()
