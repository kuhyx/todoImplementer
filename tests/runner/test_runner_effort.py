"""Effort is set per turn: high by default (kuhy, 2026-11-21), low for the classifier."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_BAD, LIVE_OK, PLAN, boot, reply, wait_stage
from tierfakes import Free
from todoimpl.runner import claude, credit, limits

CHEAP = {"title": "text-free (textgate-rework)", "done_check": "true"}
GIVE_UP = reply("Too big.\n\nESCALATE: needs a refactor")
CRASH = reply("boom", is_error=True)


def efforts(world: Env) -> list[str | None]:
    return [c["effort"] for c in world.calls()]


def implement_calls(world: Env) -> list[dict[str, Any]]:
    return [c for c in world.calls() if "Implement stage" in str(c["prompt"])]


def run_to_gate(world: Env, *turns: tuple[dict[str, Any], ...], **fields: Any) -> Any:
    sched, _ = boot(world, *turns, **fields)
    try:
        sched.start(CARD)
        return wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t1897_every_role_has_a_default_effort_and_the_argv_carries_it(tmp_path: Path) -> None:
    assert claude.ROLE_EFFORT["implement"] == "high"
    assert claude.ROLE_EFFORT["classify"] == "low"
    inv = claude.build("implement", "go", tmp_path)
    assert inv.argv[inv.argv.index("--effort") + 1] == "high"
    low = claude.build("implement", "go", tmp_path, effort="medium")
    assert low.argv[low.argv.index("--effort") + 1] == "medium"


def test_t1897_no_role_is_left_without_an_effort() -> None:
    assert set(claude.ROLE_EFFORT) == set(claude.ROLE_MODELS)


def test_t1897_the_credit_spec_carries_the_effort_to_the_sdk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    enable_credits(monkeypatch)
    inv = credit.build("implement", "go", tmp_path, effort="high")
    assert json.loads(inv.argv[-1])["effort"] == "high"


def test_t2471_every_turn_of_a_normal_run_and_its_fix_is_high(world: Env) -> None:
    run_to_gate(world, PLAN, IMPL, LIVE_BAD, IMPL, LIVE_OK, done_check="true")
    assert efforts(world) == ["high", "high", "high", "high", "high"]  # plan, impl, live, fix, live


def test_t1897_the_result_file_names_the_effort(world: Env) -> None:
    run_to_gate(world, PLAN, IMPL, LIVE_OK, done_check="true")
    results = sorted((world.root / CARD).glob("implement-*.result.json"))
    assert json.loads(results[0].read_text())["effort"] == "high"


def test_t1897_credit_turns_keep_their_effort(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    enable_credits(monkeypatch)
    limits.write_until(world.root, 4_000_000_000)
    st = run_to_gate(world, PLAN, IMPL, LIVE_OK, done_check="true")
    assert st.extra["route"] == "credits"


def test_t1897_a_cheap_run_that_gives_up_reruns_at_high_effort_on_the_same_model(
    world: Env, free: Free
) -> None:
    """kuhy, 2026-11-10: the manager is Opus, so escalation is effort (medium, then high), not a model."""
    st = run_to_gate(world, PLAN, GIVE_UP, IMPL, LIVE_OK, **CHEAP)
    first, second = implement_calls(world)
    assert (first["model"], first["effort"]) == ("opus", "medium")
    assert (second["model"], second["effort"]) == ("opus", "high")
    assert st.extra["escalated"] is True
