"""The cheap tier writes what goes wrong with the free models to the run's free-issues.jsonl."""

from __future__ import annotations

from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN
from test_runner_tier_flow import CHEAP, implement_calls, run_to_gate
from tierfakes import Free
from todoimpl.umbrella import issues


def test_the_manager_prompt_names_the_worker_command_and_the_issue_log(world: Env, free: Free) -> None:
    run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    prompt = str(implement_calls(world)[0]["prompt"])
    assert "todoimpl.runner.freeworker" in prompt
    assert f"{world.root / CARD}/free-issues.jsonl" in prompt
    assert "never raw `claude-free`" in prompt


def test_a_dead_gateway_is_logged_with_its_exact_error(world: Env, free: Free) -> None:
    free.up = False
    run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    (row,) = issues.read(world.root / CARD)
    assert (row["child"], row["phase"], row["fixed"]) == ("kuhyx/demo", "start", False)
    assert "HTTP 503" in row["symptom"]


def test_a_private_repo_is_policy_not_an_issue(world: Env, free: Free) -> None:
    free.public = False
    run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    assert issues.read(world.root / CARD) == []
