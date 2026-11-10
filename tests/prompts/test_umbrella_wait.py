"""The umbrella manager waits for its workers inside the turn; ending the turn early escalates the round."""

from __future__ import annotations

from todoimpl.prompts import PromptContext, build


def test_t1883_the_manager_waits_in_one_blocking_call_and_never_ends_its_turn_early(
    ctx: PromptContext,
) -> None:
    text = build("manager", ctx)
    assert "never end your turn" in text
    assert "never use Monitor" in text
    assert "wait <log>" in text  # T1898: one command waits for the workers
    assert "never `pgrep -f" not in text


def test_t1886_the_manager_builds_the_worktree_environment_before_the_servers_checks(
    ctx: PromptContext,
) -> None:
    text = build("manager", ctx)
    assert "no .venv or node_modules" in text
    assert "leave them in the worktree" in text


def test_t1922_the_manager_fixes_a_red_check_that_predates_the_task(ctx: PromptContext) -> None:
    text = build("manager", ctx)
    assert "never leave it red as out of scope" in text
    assert "bump each pin the dependency-freshness gate names" in text
