"""The cheap tier: which notes are cheap, the ESCALATE line, and the server's free-models verdict."""

from __future__ import annotations

import pytest
from runnerfakes import Env
from tierfakes import Free, worktree_of
from todoimpl.repotask.model import Part
from todoimpl.runner import freegate, tier


@pytest.mark.parametrize(
    ("title", "body", "cheap"),
    [
        ("Plain", "no tier here", False),
        ("Plain", "Tier: cheap", True),
        ("Plain", "intro\n  tier:   CHEAP  \nmore", True),
        ("Plain", "Tier: cheaper", False),
        ("Plain", "not a Tier: cheap line", False),
        ("Plain", "Tier: normal", False),
        ("text-free (textgate-rework)", "", True),
        ("Todo: Text-Free (Textgate-Rework) pass", "", True),
        ("text-free textgate-rework", "", False),
    ],
)
def test_is_cheap(title: str, body: str, cheap: bool) -> None:
    assert tier.is_cheap(title, body) is cheap


def _part(title: str, *, human: bool = False, held: bool = False) -> Part:
    return Part("abcd1234-0", "abcd1234", 0, title, "", "medium", None, human, held)


@pytest.mark.parametrize(
    ("parts", "cheap"),
    [
        ([_part("Make demo text-free (textgate-rework)")], True),
        ([_part("Fix it"), _part("Make demo text-free (textgate-rework)")], True),
        ([_part("Fix it")], False),
        ([_part("Make demo text-free (textgate-rework)", human=True)], False),  # kuhy's part, not the run's
        ([_part("Make demo text-free (textgate-rework)", held=True)], False),  # an older run's part
    ],
)
def test_t1999_is_cheap_reads_the_work_parts_of_a_repo_card(parts: list[Part], cheap: bool) -> None:
    assert tier.is_cheap("demo", "### Part abcd1234-0: x", parts) is cheap


def test_escalation_line() -> None:
    assert tier.escalation("work\nESCALATE: too hard for me\nD: done") == "too hard for me"
    assert tier.escalation("  escalate:   lower case ok  ") == "lower case ok"
    assert tier.escalation("ESCALATE:") == "no reason given"
    assert tier.escalation("no such line, ESCALATE: mid-line") is None
    assert tier.escalation("x" * 10) is None
    assert len(tier.escalation("ESCALATE: " + "y" * 900) or "") == tier.REASON_MAX


def test_free_allowed_for_a_public_repo_with_a_live_gateway(world: Env, free: Free) -> None:
    wt = worktree_of(world)
    assert freegate.check(wt) == freegate.Verdict(allowed=True, why="")
    assert free.checked() == [str(wt)]
    assert free.auth == [f"Bearer {'omni-test-key'}"]


def test_private_repo_means_no_free_models(world: Env, free: Free) -> None:
    free.public = False
    verdict = freegate.check(worktree_of(world))
    assert not verdict.allowed
    assert "public" in verdict.why
    assert free.auth == []  # the gateway is not even asked


def test_gateway_down_means_no_free_models(world: Env, free: Free) -> None:
    free.up = False
    verdict = freegate.check(worktree_of(world))
    assert not verdict.allowed
    assert "gateway" in verdict.why


def test_gateway_refusing_connections(world: Env, free: Free, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", "http://127.0.0.1:1")
    assert "gateway" in freegate.check(worktree_of(world)).why
    assert free.checked()


def test_missing_key_means_no_free_models(world: Env, free: Free) -> None:
    (world.home / ".config" / "omniroute" / "api_key").unlink()
    assert "key" in freegate.check(worktree_of(world)).why


def test_missing_tools_mean_no_free_models(world: Env, free: Free, monkeypatch: pytest.MonkeyPatch) -> None:
    free.remove_tools()
    monkeypatch.setenv("PATH", str(world.bin))  # kuhy's real claude-free must not leak in
    verdict = freegate.check(worktree_of(world))
    assert not verdict.allowed
    assert "claude-free" in verdict.why


def test_a_hung_check_counts_as_not_public(world: Env, free: Free, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(freegate, "CHECK_TIMEOUT", 0.01)
    slow = world.bin / "free-llm-check-dir"
    slow.write_text("#!/bin/sh\nsleep 2\n", encoding="utf-8")
    assert "public" in freegate.check(worktree_of(world)).why


def test_an_unrunnable_check_counts_as_not_public(world: Env, free: Free) -> None:
    (world.bin / "free-llm-check-dir").write_text("not a script", encoding="utf-8")
    assert "public" in freegate.check(worktree_of(world)).why
