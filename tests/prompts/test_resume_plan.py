"""A resumed session already has plan.md in its context: the prompt names the path instead of repeating it."""

from __future__ import annotations

from dataclasses import replace

import pytest
from todoimpl.prompts import PromptContext, build

CRITERION = "I click the toggle, the page turns dark."


@pytest.mark.parametrize("stage", ["implement", "fix", "live_check", "live_checklist", "live_proof"])
def test_t1891_a_fresh_session_gets_the_whole_plan(stage: str, ctx: PromptContext) -> None:
    assert CRITERION in build(stage, ctx)


@pytest.mark.parametrize("stage", ["implement", "fix", "live_check", "live_checklist", "live_proof"])
def test_t1891_a_resumed_session_gets_the_path_not_the_plan(stage: str, ctx: PromptContext) -> None:
    text = build(stage, replace(ctx, resumed=True))
    assert CRITERION not in text
    assert "/run/ab12cd34/plan.md" in text
