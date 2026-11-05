from pathlib import Path

import pytest
from runnerfakes import Env, make_repo, sh
from todoimpl.runner import worktree
from todoimpl.runner.files import NeedsYouError


def test_repo_dir_maps_kuhyx_names_to_src(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(world)
    assert worktree.repo_dir("kuhyx/demo") == repo
    assert worktree.repo_dir("demo") == repo
    monkeypatch.setenv("TODOIMPL_SRC", str(world.tmp / "elsewhere"))
    with pytest.raises(NeedsYouError, match="not cloned at") as missing:
        worktree.repo_dir("kuhyx/demo")
    assert missing.value.kind == "handed_to_you"


def test_repo_dir_refuses_no_repo_and_foreign_owners(world: Env) -> None:
    with pytest.raises(NeedsYouError, match="no repo") as none:
        worktree.repo_dir(None)
    assert none.value.kind == "handed_to_you"
    with pytest.raises(NeedsYouError, match="not a kuhyx/ repo") as foreign:
        worktree.repo_dir("someone/demo")
    assert foreign.value.kind == "run_failed"


def test_add_creates_reuses_and_removes_a_worktree(world: Env) -> None:
    repo = make_repo(world)
    origin_sha = sh(repo, "git", "rev-parse", "origin/main").strip()
    wt = worktree.add(repo, world.root, "abcd1234-0")
    assert wt.path == world.root / "abcd1234-0" / "wt"
    assert (wt.branch, wt.base_sha, wt.base_ref, wt.remote_branch) == (
        "todo/abcd1234-0",
        origin_sha,
        "origin/main",
        "main",
    )
    assert (wt.path / "README.md").exists()
    assert worktree.add(repo, world.root, "abcd1234-0") == wt
    sh(repo, "git", "worktree", "remove", "--force", str(wt.path))
    again = worktree.add(repo, world.root, "abcd1234-0")
    assert again.path.exists()
    assert sh(again.path, "git", "branch", "--show-current").strip() == "todo/abcd1234-0"
    worktree.remove(repo, again.path, again.branch)
    assert not again.path.exists()
    assert sh(repo, "git", "branch", "--list", "todo/abcd1234-0") == ""


def test_base_ref_falls_back_to_master_and_needs_an_origin(world: Env, tmp_path: Path) -> None:
    repo = make_repo(world)
    sh(repo, "git", "branch", "-m", "main", "master")
    sh(repo, "git", "push", "-q", "origin", "master")
    sh(repo, "git", "update-ref", "-d", "refs/remotes/origin/main")
    assert worktree.base_ref(repo) == ("origin/master", "master")
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    sh(lonely, "git", "init", "-q", "-b", "main")
    with pytest.raises(NeedsYouError, match="no origin/main or origin/master"):
        worktree.base_ref(lonely)


def test_git_errors_carry_stderr(world: Env, tmp_path: Path) -> None:
    with pytest.raises(worktree.GitError, match="not a git repository"):
        worktree.git(tmp_path, "status")
    assert worktree.git(tmp_path, "status", check=False).returncode != 0


def test_git_timeout_becomes_a_needs_you(world: Env, tmp_path: Path) -> None:
    hook = tmp_path / "slow"
    hook.mkdir()
    sh(hook, "git", "init", "-q")
    with pytest.raises(worktree.GitError, match="timed out"):
        worktree.git(hook, "-c", "alias.nap=!sleep 5", "nap", timeout=0.3)
