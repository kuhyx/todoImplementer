"""Shared fixtures: a fully populated context over a scratch worktree."""

from __future__ import annotations

from pathlib import Path

import pytest
from todoimpl.prompts import PromptContext


@pytest.fixture
def ctx() -> PromptContext:
    """Return a context with fixed paths so golden files stay stable."""
    return PromptContext(
        title="Add dark mode toggle",
        body="Header needs a toggle that persists.",
        repo="todo",
        worktree=Path("/wt/todo"),
        run_dir=Path("/run/ab12cd34"),
        done_check="pnpm test",
        plan_md="## Acceptance criteria\nC1. I click the toggle, the page turns dark.",
        spec_answers=(("Persist where?", "localStorage"),),
        notes=("also check mobile width",),
        failure_tail="AssertionError: C1 failed",
        handoff="Stage implement; toggle component written, persistence missing.",
    )
