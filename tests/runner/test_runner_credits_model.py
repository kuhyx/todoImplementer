"""A role held below the model it wants by the credits route says so; at the default Opus none is held."""

import json
import time

import pytest
from contract_lib import validate
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.credits import setting
from todoimpl.runner import limits


def _results(world: Env, role: str) -> list[dict[str, object]]:
    return [json.loads(p.read_text()) for p in sorted((world.root / CARD).glob(f"{role}-*.result.json"))]


def test_t1892_a_credit_turn_records_the_model_it_wanted_and_the_one_it_ran_on(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    setting.settings_path().write_text('{"credits_model": "sonnet"}')  # kuhy picks the smaller model
    limits.write_until(world.root, time.time() + 3600)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        (impl,) = _results(world, "implement")[:1]
        assert impl["model"] == "sonnet"
        assert impl["wanted_model"] == "opus"
        assert st.extra["credit_downgrade"] == {"implement": {"wanted": "opus", "ran": "sonnet"}}
        validate("state", st.to_dict())  # the new key is in the contract
        (plan,) = _results(world, "plan")
        assert plan["model"] == plan["wanted_model"] == "sonnet"
    finally:
        sched.close()


def test_t1892_a_plan_turn_runs_on_the_model_it_wanted(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert "credit_downgrade" not in st.extra
        assert _results(world, "implement")[0]["model"] == "opus"
    finally:
        sched.close()


def test_t2004_credit_turns_run_on_opus_by_default_and_hold_no_role_back(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    limits.write_until(world.root, time.time() + 3600)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        ran = {r["model"] for role in ("plan", "implement") for r in _results(world, role)}
        assert ran == {"claude-opus-5-5"}
        assert "credit_downgrade" not in st.extra  # a sonnet role on opus is an upgrade, not a hold
        assert _results(world, "implement")[0]["wanted_model"] == "opus"
    finally:
        sched.close()
