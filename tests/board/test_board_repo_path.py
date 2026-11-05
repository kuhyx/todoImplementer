"""One repo -> clone path rule shared by the board's repo check and the runner's repo_dir."""

from pathlib import Path

import pytest
from todoimpl.board.board import repo_checker
from todoimpl.board.repos import repo_path
from todoimpl.runner.worktree import repo_dir


def test_repo_path_strips_the_owner(tmp_path: Path) -> None:
    assert repo_path("kuhyx/foo", tmp_path) == tmp_path / "foo"
    assert repo_path("foo", tmp_path) == tmp_path / "foo"


def test_repo_path_defaults_to_env_then_home_src(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path))
    assert repo_path("kuhyx/foo") == tmp_path / "foo"
    monkeypatch.delenv("TODOIMPL_SRC")
    assert repo_path("kuhyx/foo") == Path.home() / "src" / "foo"


def test_t202_board_and_runner_agree_on_the_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "foo" / ".git").mkdir(parents=True)
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path))
    assert repo_dir("kuhyx/foo") == tmp_path / "foo"
    assert repo_checker()("kuhyx/foo") is None
    assert repo_checker()("kuhyx/missing") == str(tmp_path / "missing")
