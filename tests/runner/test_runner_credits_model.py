"""A role held below the model it wants by the credits route says so; at the default Sonnet none is held."""

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
    setting.settings_path().write_text('{"credits_model": "haiku"}')  # kuhy picks the smaller model
    limits.write_until(world.root, time.time() + 3600)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        (impl,) = _results(world, "implement")[:1]
        assert impl["model"] == "haiku"
        assert impl["wanted_model"] == "sonnet"
        down = {"wanted": "sonnet", "ran": "haiku"}  # every card role wants Sonnet (T2615)
        assert st.extra["credit_downgrade"] == {"plan": down, "implement": down, "live_check": down}
        validate("state", st.to_dict())  # the new key is in the contract
        (plan,) = _results(world, "plan")
        assert (plan["model"], plan["wanted_model"]) == ("haiku", "sonnet")
    finally:
        sched.close()


def test_t1892_a_plan_turn_runs_on_the_model_it_wanted(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert "credit_downgrade" not in st.extra
        assert _results(world, "implement")[0]["model"] == "sonnet"
    finally:
        sched.close()


def test_t2615_credit_turns_run_on_sonnet_by_default_and_hold_no_role_back(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    limits.write_until(world.root, time.time() + 3600)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        ran = {r["model"] for role in ("plan", "implement") for r in _results(world, role)}
        assert ran == {"claude-sonnet-5-5"}
        assert "credit_downgrade" not in st.extra  # a sonnet role on sonnet is no hold
        assert _results(world, "implement")[0]["wanted_model"] == "sonnet"
    finally:
        sched.close()
