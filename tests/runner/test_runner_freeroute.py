"""The `free` route: a public card goes on through claude-free while the plan is out (T2531)."""

import json
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from runnerfakes import SHIMS, Env, executable
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, lift_limit, state, wait_stage
from todoimpl.board.badges import tier_badges
from todoimpl.board.card import current_line
from todoimpl.board.state import RunState
from todoimpl.board.status import Status
from todoimpl.runner import freeok, freeworker, limits


def free_world(world: Env, monkeypatch: pytest.MonkeyPatch, visibility: str = "PUBLIC") -> None:
    """Plan limited, credits off, kuhyx/demo cached as `visibility`, the gateway up, a claude-free shim."""
    limits.write_until(world.root, time.time() + 3600)
    cache = Path.home() / ".cache" / "omniroute_offload" / "visibility.json"
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(
        json.dumps({"kuhyx/demo": {"visibility": visibility, "at": time.time()}}), encoding="utf-8"
    )
    shim = world.bin / "claude-free"
    executable(shim, f'#!/bin/sh\nexec "{sys.executable}" "{SHIMS / "claude"}" "$@"\n')
    monkeypatch.setenv("TODOIMPL_FREE_CLAUDE", str(shim))
    monkeypatch.setattr(freeok, "gateway_up", lambda: True)


def test_t2531_a_limited_public_card_runs_free_and_waits_for_claude_to_verify(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    free_world(world, monkeypatch)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "paused_limit", turns=3)
        calls = world.calls()
        assert [c["model"] for c in calls] == ["free-best"] * 3
        assert freeworker.PREAMBLE in calls[0]["prompt"]
        assert st.extra["route"] == "free"
        assert st.extra["free_unverified"] is True
        assert st.extra["resume_stage"] == "checks"
        assert st.cost_usd == 0.0
        lift_limit(world, sched)
        st = wait_stage(world, sched, "gate", turns=2)
        verify = world.calls()[3]
        assert verify["model"] == "opus"
        assert verify["resume"] is None  # a fresh Claude session, never the free one
        assert "free_unverified" not in st.extra
    finally:
        sched.close()


def test_t2531_a_private_card_keeps_waiting(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    free_world(world, monkeypatch, visibility="PRIVATE")
    sched, _ = boot(world, PLAN)
    try:
        sched.start(CARD)
        time.sleep(1.0)
        assert world.calls() == []
        assert state(world).stage == "spec"
    finally:
        sched.close()


def test_t2531_an_error_fix_never_goes_free(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    free_world(world, monkeypatch)
    sched, _ = boot(world, PLAN, body="Error-Signature: abc\n")
    try:
        sched.start(CARD)
        time.sleep(1.0)
        assert world.calls() == []
    finally:
        sched.close()


def test_t2531_the_card_says_it_waits_for_claude_and_shows_the_free_badge() -> None:
    run = RunState(task_id=CARD, stage="paused_limit", extra={"free_unverified": True, "route": "free"})
    assert current_line(Status.PAUSED_LIMIT, run, None, 0.0) == "waits for Claude verify"
    assert tier_badges(SimpleNamespace(title="x", body="", parts=()), run)["free"] is True
