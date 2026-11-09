"""Machine-local, git-ignored files (tunedeck's android/local.properties) follow the repo into task worktrees."""

from pathlib import Path

from runnerfakes import Env, make_repo, sh
from todoimpl.runner import worktree

LOCAL = "chaquopy.buildPython=/usr/bin/python3\n"


def _repo_with_local(world: Env, ignore: str = "/local.properties\n") -> Path:
    """A clone whose android/ dir ignores local.properties and holds a machine-local copy."""
    repo = make_repo(world, files={".gitignore": "x\n"})
    (repo / "android").mkdir()
    (repo / "android" / ".gitignore").write_text(ignore, encoding="utf-8")
    sh(repo, "git", "add", "-A")
    sh(repo, "git", "commit", "-q", "-m", "android")
    sh(repo, "git", "push", "-q", "origin", "main")
    (repo / "android" / "local.properties").write_text(LOCAL, encoding="utf-8")
    return repo


def test_t1860_worktree_gets_the_machine_local_properties(world: Env) -> None:
    repo = _repo_with_local(world)
    wt = worktree.add(repo, world.root, "abcd1234-0")
    assert (wt.path / "android" / "local.properties").read_text(encoding="utf-8") == LOCAL
    assert sh(wt.path, "git", "status", "--porcelain") == ""  # ignored: it can never be committed


def test_local_properties_never_overwrite_or_follow_other_files(world: Env) -> None:
    repo = _repo_with_local(world)
    (repo / "android" / "secret.txt").write_text("nope\n", encoding="utf-8")
    wt = worktree.add(repo, world.root, "abcd1234-0")
    (wt.path / "android" / "local.properties").write_text("mine\n", encoding="utf-8")
    worktree.add(repo, world.root, "abcd1234-0")  # reuse: the worktree's own copy stays
    assert (wt.path / "android" / "local.properties").read_text(encoding="utf-8") == "mine\n"
    assert not (wt.path / "android" / "secret.txt").exists()


def test_local_properties_not_ignored_are_not_copied(world: Env) -> None:
    """A copy that git does not ignore would show up in `git add -A` and be shipped."""
    repo = _repo_with_local(world, ignore="# nothing ignored\n")
    wt = worktree.add(repo, world.root, "abcd1234-0")
    assert not (wt.path / "android" / "local.properties").exists()


def test_a_repo_without_local_properties_is_untouched(world: Env) -> None:
    wt = worktree.add(make_repo(world), world.root, "abcd1234-0")
    assert not list(wt.path.rglob("local.properties"))
