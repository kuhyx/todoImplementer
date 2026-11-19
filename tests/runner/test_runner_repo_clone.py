"""T2079: a run whose repo has no checkout anywhere clones it (gh repo clone) before its worktree."""

from pathlib import Path

import pytest
from runnerfakes import Env, make_repo
from todoimpl.board import clone
from todoimpl.board.state import RunState
from todoimpl.runner import worktree
from todoimpl.runner.files import NeedsYouError


def test_t2079_repo_dir_clones_a_missing_repo_into_src(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, Path]] = []
    seed = make_repo(world, "seed")

    def fake_clone(repo: str, dest: Path) -> None:
        calls.append((repo, dest))
        seed.rename(dest)

    monkeypatch.setattr(clone, "gh_clone", fake_clone)
    assert worktree.repo_dir("kuhyx/fresh", clone=True) == world.src / "fresh"
    assert calls == [("kuhyx/fresh", world.src / "fresh")]
    assert worktree.repo_dir("kuhyx/fresh", clone=True) == world.src / "fresh"  # present now: no second clone
    assert len(calls) == 1


def test_t2079_no_clone_unless_asked(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(clone, "gh_clone", lambda *_: pytest.fail("cloned"))
    with pytest.raises(NeedsYouError, match="not cloned at"):
        worktree.repo_dir("kuhyx/fresh")


def test_t2079_a_failed_clone_names_the_error(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(repo: str, dest: Path) -> None:
        msg = "gh repo clone failed: Could not resolve to a Repository"
        raise OSError(msg)

    monkeypatch.setattr(clone, "gh_clone", refuse)
    with pytest.raises(NeedsYouError, match="Could not resolve to a Repository") as err:
        worktree.repo_dir("kuhyx/ghost", clone=True)
    assert "kuhyx/ghost" in str(err.value)
    assert err.value.kind == "run_failed"


def test_t2079_attach_makes_the_worktree_in_a_fresh_clone(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = make_repo(world, "seed")
    monkeypatch.setattr(clone, "gh_clone", lambda _repo, dest: seed.rename(dest))
    st = RunState(task_id="abcd1234-0", stage="implement")
    worktree.attach(st, "kuhyx/fresh", world.root)
    assert (world.src / "fresh" / ".git").exists()
    assert Path(str(st.worktree)).is_dir()


def test_t2079_gh_clone_runs_gh_repo_clone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shim = tmp_path / "bin" / "gh"
    shim.parent.mkdir()
    shim.write_text(
        '#!/bin/sh\necho "$@" > "$GH_LOG"\n[ "$3" = bad/repo ] && { echo boom >&2; exit 1; }\nexit 0\n',
        encoding="utf-8",
    )
    shim.chmod(0o755)
    monkeypatch.setattr(clone, "GH", str(shim))
    monkeypatch.setenv("GH_LOG", str(tmp_path / "log"))
    dest = tmp_path / "dest"
    clone.gh_clone("kuhyx/claude-config", dest)
    assert (tmp_path / "log").read_text(encoding="utf-8").split() == [
        "repo",
        "clone",
        "kuhyx/claude-config",
        str(dest),
    ]
    with pytest.raises(OSError, match="boom"):
        clone.gh_clone("bad/repo", dest)
    monkeypatch.setattr(clone, "GH", str(tmp_path / "nothing"))
    with pytest.raises(OSError, match="gh"):
        clone.gh_clone("kuhyx/x", dest)
