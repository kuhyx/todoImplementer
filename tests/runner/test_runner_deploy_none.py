"""T2342: `- deploy: none (<reason>)` says a repo has nothing to deploy; Ship accepts it as deployed."""

from __future__ import annotations

from pathlib import Path

import pytest
from runnerfakes import Env, make_repo, sh
from todoimpl.runner import deploy, deployline, worktree

CARD = "abcd1234-0"
NONE_MD = (
    "# demo\n\n## Commands\n\n- run: `./run.sh`\n- deploy: none (a LaTeX CV: nothing runs or installs)\n"
)


def test_t2342_the_none_form_needs_a_reason_and_is_read_as_the_declared_command() -> None:
    assert deployline.declared(NONE_MD) == "none (a LaTeX CV: nothing runs or installs)"
    assert deployline.declared("- deploy: none\n") is None  # no reason: no declaration
    assert deployline.declared("- deploy: none ()\n") is None
    assert deployline.declared("```\n- deploy: none (fenced)\n```\n") is None
    assert deployline.is_none("none (a LaTeX CV: nothing runs or installs)") is True
    assert deployline.is_none("scripts/deploy.sh") is False


def test_t2342_a_none_deploy_passes_without_starting_any_unit(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    make_repo(world, files={"README.md": "demo\n", "CLAUDE.md": NONE_MD})
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    wt = worktree.add(world.src / "demo", world.root, CARD).path

    def never(*_a: object) -> None:
        raise AssertionError

    monkeypatch.setattr(deploy, "_start", never)
    result = deploy.run(wt, world.root / CARD, CARD, "kuhyx/demo")
    assert result.passed
    assert result.command == "none (a LaTeX CV: nothing runs or installs)"
    assert "nothing to deploy" in result.tail
    assert not Path(world.tmp / "deploys").exists()
    assert sh(wt, "git", "status", "--porcelain").strip() == ""
