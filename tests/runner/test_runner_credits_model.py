"""A role that wants Opus but runs on Sonnet because of the credits route says so (kuhy's rule)."""

import json
import time

import pytest
from contract_lib import validate
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.runner import limits


def _results(world: Env, role: str) -> list[dict[str, object]]:
    return [json.loads(p.read_text()) for p in sorted((world.root / CARD).glob(f"{role}-*.result.json"))]


def test_t1892_a_credit_turn_records_the_model_it_wanted_and_the_one_it_ran_on(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
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
