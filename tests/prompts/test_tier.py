"""The cheap-tier addendum rides on the implement-role prompts only."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from todoimpl.prompts import STAGES, PromptContext, build
from todoimpl.prompts import tier as texts


@pytest.mark.parametrize("stage", ["implement", "fix", "resume_after_kill", "fresh_after_idle"])
def test_addendum_is_appended_to_implement_prompts(stage: str, ctx: PromptContext) -> None:
    text = build(stage, replace(ctx, tier="TIER-NOTE"))
    assert text.endswith("\nTIER-NOTE")
    assert text.removesuffix("\nTIER-NOTE") == build(stage, ctx)


@pytest.mark.parametrize(
    "stage", sorted(STAGES.keys() - {"implement", "fix", "resume_after_kill", "fresh_after_idle"})
)
def test_other_stages_never_carry_it(stage: str, ctx: PromptContext) -> None:
    assert build(stage, replace(ctx, tier="TIER-NOTE")) == build(stage, ctx)


def test_manager_names_the_worker_command_the_checks_the_issue_log_and_the_give_up_line() -> None:
    text = texts.manager(Path("/wt/x"), Path("/run/r1"), "W-CMD", "kuhyx/x")
    assert "W-CMD /wt/x <sub-task file> /run/r1/worker-<n>.log --issues /run/r1 --child kuhyx/x" in text
    assert "never raw `claude-free`" in text
    assert "/run/r1/free-issues.jsonl" in text
    assert "git diff" in text
    assert "permission block" in text
    assert "ESCALATE: <reason>" in text


def test_alone_says_why_and_forbids_the_worker() -> None:
    text = texts.alone("the repo is not public")
    assert "the repo is not public" in text
    assert "no claude-free" in text
    assert "ESCALATE: <reason>" in text


def test_escalated_carries_the_reason() -> None:
    text = texts.escalated("tests need a design call")
    assert "tests need a design call" in text
    assert "git diff" in text
    assert "<reason>" not in text
