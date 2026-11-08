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


def make_clone(root: Path, directory: str, url: str | None) -> Path:
    git = root / directory / ".git"
    git.mkdir(parents=True)
    if url is not None:
        config = f'[core]\n\tbare = false\n[remote "origin"]\n\turl = {url}\n\tfetch = +refs/*:refs/*\n'
        (git / "config").write_text(config, encoding="utf-8")
    return root / directory


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/kuhyx/todo-app.git",
        "https://github.com/kuhyx/todo-app",
        "git@github.com:kuhyx/todo-app.git",
        "ssh://git@github.com/kuhyx/todo-app.git",
    ],
)
def test_t1402_finds_a_clone_in_a_differently_named_directory(tmp_path: Path, url: str) -> None:
    clone = make_clone(tmp_path, "todo", url)
    assert repo_path("kuhyx/todo-app", tmp_path) == clone


def test_t1402_ignores_other_remotes_and_unreadable_configs(tmp_path: Path) -> None:
    make_clone(tmp_path, "a", "https://github.com/kuhyx/todo-app-extra.git")
    make_clone(tmp_path, "b", "https://github.com/other/todo-app.git")
    make_clone(tmp_path, "c", None)
    (tmp_path / "d" / ".git" / "config").mkdir(parents=True)
    (tmp_path / "plain").mkdir()
    (tmp_path / "file.txt").write_text("x", encoding="utf-8")
    assert repo_path("kuhyx/todo-app", tmp_path) == tmp_path / "todo-app"


def test_t1402_exact_directory_wins_and_cache_follows_a_moved_clone(tmp_path: Path) -> None:
    first = make_clone(tmp_path, "todo", "git@github.com:kuhyx/todo-app.git")
    assert repo_path("kuhyx/todo-app", tmp_path) == first
    assert repo_path("kuhyx/todo-app", tmp_path) == first  # served from the cache
    first.rename(tmp_path / "moved")
    assert repo_path("kuhyx/todo-app", tmp_path) == tmp_path / "moved"
    exact = make_clone(tmp_path, "todo-app", None)
    assert repo_path("kuhyx/todo-app", tmp_path) == exact
    assert repo_path("kuhyx/nothing", tmp_path / "absent") == tmp_path / "absent" / "nothing"


def test_t1839_the_runner_finds_a_clone_in_a_differently_named_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    clone = make_clone(tmp_path, "todo", "https://github.com/kuhyx/todo-app.git")
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path))
    assert repo_dir("kuhyx/todo-app") == clone
    assert repo_dir("todo-app") == clone
    assert repo_checker()("kuhyx/todo-app") is None


def test_t1839_a_directory_with_another_origin_loses_to_the_matching_clone(tmp_path: Path) -> None:
    wrong = make_clone(tmp_path, "todo-app", "https://github.com/kuhyx/other.git")
    assert repo_path("kuhyx/todo-app", tmp_path) == wrong  # nothing better: the name still wins
    real = make_clone(tmp_path, "todo", "git@github.com:kuhyx/todo-app.git")
    assert repo_path("kuhyx/todo-app", tmp_path) == real
    (wrong / ".git" / "config").write_text(
        '[remote "origin"]\n\turl = https://github.com/kuhyx/todo-app.git\n', encoding="utf-8"
    )
    assert repo_path("kuhyx/todo-app", tmp_path) == wrong
