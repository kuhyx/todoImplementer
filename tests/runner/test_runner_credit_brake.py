"""The credit brake end to end: the cap cuts a running credit turn, the plan goes on; near it, one at once."""

import json
import time
from pathlib import Path

import pytest
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait, wait_stage
from todoimpl.credits import ledger, live, pacing, route
from todoimpl.runner import limits

BIG = {
    "type": "assistant",
    "message": {"id": "msg_big", "usage": {"input_tokens": 10, "output_tokens": 100_000_000}, "content": []},
}  # a hundred million output tokens: far past any cap
HOLD = ({"_fake": "raw", "text": json.dumps(BIG)}, {"_fake": "sleep", "sec": 30})


def test_cap_crossed_mid_turn_stops_the_credit_turn_and_the_plan_goes_on_in_the_same_session(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    sched, _ = boot(world, HOLD, PLAN, IMPL, LIVE_OK, done_check="true")
    began = time.monotonic()
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert time.monotonic() - began < 25  # the first turn would have slept 30 s: it was cut, not awaited
        calls = world.calls()
        assert [c["via_sdk"] for c in calls] == [True, False, False, False]
        assert calls[1]["resume"]  # the stopped turn's session goes on
        assert "(runner) Continue" in calls[1]["prompt"]
        first = next((world.root / CARD).glob("plan-*.stream.jsonl"))
        ended = json.loads(first.with_name(first.name.replace(".stream.jsonl", ".exit.json")).read_text())[
            "ended"
        ]
        assert ended - first.stat().st_mtime < 3  # the stop fires within a poll (50 ms) plus the kill
        assert st.extra["route"] == "plan"
        assert "cap_hit" not in st.extra
        stopped = next(t for t in ledger.book(world.root).turns.values() if t.route == "credits")
        assert stopped.cumulative_usd is None  # it never reached a result event
        assert stopped.delta_usd > 1000  # but its usage was paid for in the credit spend
        assert live.running(world.root) == 0
    finally:
        sched.close()


def test_cap_crossed_with_the_plan_limited_pauses_instead_of_spending_on(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    limits.write_until(world.root, time.time() + 3600)
    sched, _ = boot(world, HOLD, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "paused_limit")
        assert [c["via_sdk"] for c in world.calls()] == [True]
        wait(lambda: live.running(world.root) == 0)
    finally:
        sched.close()


def test_within_twenty_dollars_of_the_cap_a_second_credit_turn_goes_to_the_plan(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    now = time.time()
    near = pacing.pace(world.root, now).cap_usd - 10.0  # $10 below the cap, inside the $20 window
    ledger.record(
        world.root, task="old00000-0", stem="implement-1.000", role="implement", route="credits",
        session_id=None, cumulative=near / pacing.pace(world.root, now).cost_factor, ended_at=now,
    )  # fmt: skip
    live.begin(world.root, "other000-0")  # another card has a credit turn running
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert [c["via_sdk"] for c in world.calls()] == [False, False, False]
        assert st.extra["route"] == "plan"
    finally:
        sched.close()


def test_a_claim_lost_to_another_card_waits_and_the_run_goes_on_when_room_is_back(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    real, lost = route.claim, list[str]()

    def claim(root: Path, now: float, card: str) -> route.Choice:
        if not lost:  # another card took the last of the pace between the decision and the start
            lost.append(card)
            return route.Choice(None, now + 1)
        return real(root, now, card)

    monkeypatch.setattr(route, "claim", claim)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate", turns=3)
        assert lost == [CARD]
        assert [c["via_sdk"] for c in world.calls()] == [True, True, True]
    finally:
        sched.close()
