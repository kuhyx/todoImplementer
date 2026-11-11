"""Every finished turn lands in the credit ledger on either route; result.json keeps the stream's totals."""

import json
import time

import pytest
from creditfakes import enable_credits, reach_cap
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.credits import ledger


def _results(world: Env, role: str = "") -> list[dict[str, object]]:
    return [json.loads(p.read_text()) for p in sorted((world.root / CARD).glob(f"{role}*.result.json"))]


def _ledger_lines(world: Env) -> list[dict[str, object]]:
    text = (world.root / ledger.LEDGER_FILE).read_text()
    return [json.loads(line) for line in text.splitlines()]


def test_t1990_a_credit_turn_result_keeps_the_total_cost_and_model_usage_of_its_stream(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    usage = {"claude-sonnet-5-5": {"inputTokens": 12, "costUSD": 0.25}}
    paid = (
        {
            "_fake": "result",
            "text": "- [x] C1: ran `cat hello.txt` -> saw hi\n\nD: done",
            "cost": 0.25,
            "model_usage": usage,
        },
    )
    sched, _ = boot(world, PLAN, IMPL, paid, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        (last,) = _results(world, "live")
        assert last["route"] == "credits"
        assert last["total_cost_usd"] == 0.25
        assert last["model_usage"] == usage
    finally:
        sched.close()


def test_every_turn_is_a_ledger_line_on_both_routes_with_its_own_delta(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        lines = _ledger_lines(world)
        assert [x["route"] for x in lines] == ["credits"] * 3
        assert {x["task"] for x in lines} == {CARD}
        assert all(
            x["delta_usd"] == x["cumulative_usd"] == 0.01 for x in lines
        )  # each fake turn is its own session
        assert ledger.spent(world.root, 0.0) == pytest.approx(0.03)
        assert ledger.turns(world.root, 0.0) == 3
    finally:
        sched.close()


def test_plan_turns_are_in_the_ledger_but_not_in_the_credit_spend(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    reach_cap(world.root)
    before = time.time()
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        mine = [x for x in _ledger_lines(world) if x["task"] == CARD]
        assert [x["route"] for x in mine] == ["plan"] * 3
        assert ledger.spent(world.root, before) == 0.0
        assert ledger.spent(world.root, before, route="plan") == pytest.approx(0.03)
    finally:
        sched.close()
