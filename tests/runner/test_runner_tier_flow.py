"""The cheap tier end to end: Sonnet (high effort) manages free models, escalation = xhigh effort (T2476)."""

from __future__ import annotations

import json
from typing import Any

from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait_stage
from tierfakes import Free

CHEAP = {"title": "text-free (textgate-rework)", "done_check": "true"}
GIVE_UP = reply("Too big for the free models.\n\nESCALATE: needs a refactor across modules")
CRASH = reply("boom", is_error=True)


def implement_calls(world: Env) -> list[dict[str, Any]]:
    return [c for c in world.calls() if "Implement stage" in str(c["prompt"])]


def effort(call: dict[str, Any]) -> str | None:
    """Return the `--effort` value of a recorded claude call, None when it has none."""
    argv = list(call["argv"])
    return str(argv[argv.index("--effort") + 1]) if "--effort" in argv else None


def feed(world: Env) -> str:
    return (world.root / CARD / "events.jsonl").read_text(encoding="utf-8")


def run_to_gate(world: Env, *turns: tuple[dict[str, Any], ...], **fields: Any) -> Any:
    sched, _ = boot(world, *turns, **fields)
    try:
        sched.start(CARD)
        return wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t2476_cheap_note_runs_sonnet_high_with_the_manager_addendum(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    impl = implement_calls(world)
    assert [c["model"] for c in impl] == ["sonnet"]
    assert [effort(c) for c in impl] == ["high"]
    assert "todoimpl.runner.freeworker" in str(impl[0]["prompt"])
    assert free.checked() == [st.worktree]
    assert (st.extra["tier"], st.extra["free_models"]) == ("cheap", True)
    assert not st.extra.get("escalated")
    assert "tier cheap" in feed(world)


def test_live_check_of_a_cheap_run_is_its_own_sonnet_high_session_without_the_addendum(
    world: Env, free: Free
) -> None:
    run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    live = world.calls()[2]
    assert (live["model"], effort(live)) == ("sonnet", "high")  # T1896, T2471
    assert "claude-free" not in str(live["prompt"])


def test_tier_line_in_the_note_body_makes_it_cheap(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, body="Do it.\nTier: cheap", done_check="true")
    assert st.extra["tier"] == "cheap"
    assert implement_calls(world)[0]["model"] == "sonnet"


def test_private_repo_means_claude_alone(world: Env, free: Free) -> None:
    free.public = False
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    prompt = str(implement_calls(world)[0]["prompt"])
    assert "no claude-free" in prompt
    assert "claude-free -p" not in prompt
    assert st.extra["free_models"] is False
    assert "not public" in feed(world)


def test_gateway_down_means_claude_alone(world: Env, free: Free) -> None:
    free.up = False
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, **CHEAP)
    assert "claude-free -p" not in str(implement_calls(world)[0]["prompt"])
    assert st.extra["free_models"] is False


def test_t2476_escalate_line_reruns_the_attempt_with_more_effort(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, GIVE_UP, IMPL, LIVE_OK, **CHEAP)
    first, second = implement_calls(world)
    assert (first["model"], second["model"]) == ("sonnet", "sonnet")
    assert (effort(first), effort(second)) == ("high", "xhigh")
    assert "needs a refactor across modules" in str(second["prompt"])
    assert "claude-free -p" not in str(second["prompt"])
    assert st.extra["escalated"] is True
    assert st.extra["escalate_reason"] == "needs a refactor across modules"
    assert (world.calls()[-1]["model"], effort(world.calls()[-1])) == (
        "sonnet",
        "high",
    )  # live check: own role (T2471)
    assert "escalated" in feed(world)


def test_only_one_escalation_per_run(world: Env, free: Free) -> None:
    again = reply("Still stuck.\n\nESCALATE: nope\n\nD: partial")
    st = run_to_gate(world, PLAN, GIVE_UP, again, LIVE_OK, **CHEAP)
    assert [c["model"] for c in implement_calls(world)] == ["sonnet", "sonnet"]
    assert st.extra["escalate_reason"] == "needs a refactor across modules"


def test_a_failed_cheap_turn_escalates_the_retry(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, CRASH, IMPL, LIVE_OK, **CHEAP)
    assert [c["model"] for c in implement_calls(world)] == ["sonnet", "sonnet"]
    assert st.extra["escalated"] is True
    assert "failed" in st.extra["escalate_reason"]


def test_an_escalated_run_does_not_escalate_again_on_failure(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, GIVE_UP, CRASH, IMPL, LIVE_OK, **CHEAP)
    assert [c["model"] for c in implement_calls(world)] == ["sonnet", "sonnet", "sonnet"]
    assert st.extra["escalate_reason"] == "needs a refactor across modules"


def test_ordinary_note_is_untouched(world: Env, free: Free) -> None:
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, done_check="true")
    assert [c["model"] for c in implement_calls(world)] == ["sonnet"]
    assert effort(implement_calls(world)[0]) == "high"  # T1897: every role has a default (T2471: high)
    assert "claude-free" not in str(implement_calls(world)[0]["prompt"])
    assert st.extra["tier"] == "normal"
    assert not {"free_models", "escalated"} & set(st.extra)
    assert free.checked() == []
    assert "tier" not in feed(world).lower()


def test_state_stays_valid_json_with_the_tier_keys(world: Env, free: Free) -> None:
    run_to_gate(world, PLAN, GIVE_UP, IMPL, LIVE_OK, **CHEAP)
    saved = json.loads((world.root / CARD / "state.json").read_text(encoding="utf-8"))
    assert (saved["tier"], saved["free_models"], saved["escalated"]) == ("cheap", True, True)
    assert state(world).extra["escalated"] is True
