"""Edges of the chores: unreadable cards, failing git steps, a spent budget, a context without tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from nolimitfakes import card_tree, kuhy_repo, script_steps
from runnerfakes import Env, executable
from todoimpl.board.state import RunState
from todoimpl.nolimit import cards, context, prune, rebase, visibility

if TYPE_CHECKING:
    from collections.abc import Callable

NOW = 1_800_000_000.0


def always() -> bool:
    return True


def spent() -> Callable[[], float]:
    """Return a clock that reads 0 once, then 100 s: past every chore's budget."""
    reads = iter([0.0, 100.0])
    return lambda: next(reads)


def test_cards_without_a_readable_state_or_a_tree_are_not_cards(world: Env, tmp_path: Path) -> None:
    root = world.root
    (root / "bad").mkdir(parents=True)
    (root / "bad" / "state.json").write_text("{not json", encoding="utf-8")
    (root / "gone").mkdir()
    st = RunState(task_id="gone", stage="paused_limit", repo="kuhyx/demo", worktree=str(tmp_path / "nowhere"))
    (root / "gone" / "state.json").write_text(json.dumps(st.to_dict()), encoding="utf-8")
    assert cards.all_cards(root) == []


@pytest.mark.parametrize(
    ("step", "what"), [("prune-du", "kept: git failed"), ("prune-remove", "kept: remove failed")]
)
def test_prune_keeps_a_tree_when_git_fails_or_will_not_remove(
    world: Env, monkeypatch: pytest.MonkeyPatch, step: str, what: str
) -> None:
    kuhy_repo(world, test="true")
    tree = card_tree(world, "aaaa0001-0", stage="done_manually")
    [card] = cards.all_cards(world.root)
    script_steps(monkeypatch, {step: 1})
    assert prune.prune_card(card) == (what, 0)
    assert tree.exists()


def test_rebase_skips_a_card_whose_fetch_fails(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    card_tree(world, "bbbb0001-0")
    script_steps(monkeypatch, {"rebase-fetch": 1})
    assert rebase.run(world.root, always, NOW) == {"cards": {"bbbb0001-0": "skipped: fetch failed"}}


def test_context_skips_a_card_whose_head_git_cannot_read(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    card_tree(world, "cccc0001-0")
    script_steps(monkeypatch, {"context-head": 1})
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0001-0": "skipped: git failed"}}


def test_context_has_no_test_block_without_a_test_changed_command(world: Env) -> None:
    kuhy_repo(world, test="true")
    card_tree(world, "cccc0002-0")
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0002-0": "written"}}
    text = context.path(world.root / "cccc0002-0").read_text(encoding="utf-8")
    assert "## Uncommitted files" in text
    assert "test-changed" not in text


def test_context_names_no_failing_tests_when_the_changed_tests_pass(world: Env) -> None:
    kuhy_repo(world, test="true", test_changed="echo all fine")
    card_tree(world, "cccc0003-0")
    assert context.run(world.root, always, NOW) == {"cards": {"cccc0003-0": "written"}}
    text = context.path(world.root / "cccc0003-0").read_text(encoding="utf-8")
    assert "all fine" in text
    assert "Failing tests" not in text


def test_a_spent_budget_ends_the_rebase_and_context_chores_before_the_first_card(world: Env) -> None:
    kuhy_repo(world, test="true")
    card_tree(world, "dddd0001-0")
    assert rebase.run(world.root, always, NOW, spent()) == {"cards": {}}
    assert context.run(world.root, always, NOW, spent()) == {"cards": {}}


def test_a_spent_budget_ends_the_visibility_chore_with_the_repo_left(world: Env) -> None:
    executable(world.bin / visibility.TOOL, "#!/bin/sh\nexit 0\n")
    kuhy_repo(world, test="true")
    assert visibility.run(always, NOW, spent()) == {"refreshed": [], "failed": [], "stale_left": 1}
