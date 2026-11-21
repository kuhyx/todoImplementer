"""A resting run frees its disk (T2433): every `<run>/wt*` worktree, landed branches and venvs go."""

from __future__ import annotations

from pathlib import Path

import pytest
from runnerfakes import Env, make_repo, sh
from todoimpl.board import state as store
from todoimpl.runner import orphans, reap
from todoimpl.runner.worktree import GitError, git


def run_dir(world: Env, stage: str = "shipped", card: str = "abcd1234-0") -> Path:
    d = world.root / card
    d.mkdir(parents=True)
    store.save(d, store.RunState(task_id=card, stage=stage))
    (d / "events.jsonl").write_text("{}\n", encoding="utf-8")
    return d


def worktree(repo: Path, run: Path, name: str, branch: str, *, commit: bool = False) -> Path:
    wt = run / name
    sh(repo, "git", "worktree", "add", "-q", "-b", branch, str(wt), "origin/main")
    if commit:
        (wt / "work.txt").write_text("work\n", encoding="utf-8")
        sh(wt, "git", "add", "-A")
        sh(wt, "git", "commit", "-q", "-m", "work")
    return wt


def branches(repo: Path) -> list[str]:
    return sh(repo, "git", "branch", "--format=%(refname:short)").split()


@pytest.fixture(autouse=True)
def _no_live_cwds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reap, "live_cwds", list)


def test_t2433_a_shipped_run_loses_every_worktree_landed_branch_and_venv(world: Env) -> None:
    repo, other = make_repo(world), make_repo(world, "other")
    run = run_dir(world)
    worktree(repo, run, "wt", "todo/abcd1234-0")
    side = worktree(other, run, "wt-other", "todo/abcd1234-side", commit=True)
    sh(side, "git", "push", "-q", "origin", "HEAD:main")  # the session landed it
    (run / "venv" / "lib").mkdir(parents=True)
    (run / "venv" / "pyvenv.cfg").write_text("home = /usr\n", encoding="utf-8")
    (run / "web" / "node_modules").mkdir(parents=True)
    (run / "node_modules").mkdir()
    rep = reap.clean(run, apply=True)
    assert sorted(p.name for p in run.iterdir() if not p.name.startswith(".")) == [
        "events.jsonl",
        "state.json",
        "web",
    ]
    assert (branches(repo), branches(other)) == (["main"], ["main"])
    assert rep.removed == [str(run / "wt"), str(side)]
    assert sorted(rep.payload) == [str(run / "node_modules"), str(run / "venv")]
    assert "worktrees" not in sh(other, "git", "worktree", "list")


def test_t2433_an_unpushed_branch_is_kept_and_a_dirty_worktree_stays(world: Env) -> None:
    repo = make_repo(world)
    run = run_dir(world, "cancelled")
    worktree(repo, run, "wt", "todo/abcd1234-0", commit=True)
    dirty = worktree(repo, run, "wt-dirty", "todo/abcd1234-dirty")
    (dirty / "half.txt").write_text("half\n", encoding="utf-8")
    rep = reap.clean(run, apply=True)
    assert not (run / "wt").exists()
    assert dirty.is_dir()
    assert "todo/abcd1234-0" in branches(repo)
    assert rep.kept == ["todo/abcd1234-0"]
    assert [s.split(":")[0] for s in rep.skipped] == [str(dirty)]


def test_t2433_a_squash_landed_branch_is_deleted(world: Env) -> None:
    repo = make_repo(world)
    run = run_dir(world, "closed")
    wt = worktree(repo, run, "wt-x", "todo/abcd1234-x", commit=True)
    sh(repo, "git", "cherry-pick", sh(wt, "git", "rev-parse", "HEAD").strip())
    sh(repo, "git", "commit", "-q", "--amend", "-m", "squashed")
    sh(repo, "git", "push", "-q", "origin", "main")
    reap.clean(run, apply=True)
    assert branches(repo) == ["main"]


def test_t2433_a_dry_run_changes_nothing(world: Env) -> None:
    repo = make_repo(world)
    run = run_dir(world, "done_manually")
    wt = worktree(repo, run, "wt", "todo/abcd1234-0")
    rep = reap.clean(run, apply=False)
    assert wt.is_dir()
    assert rep.removed == [str(wt)]
    assert rep.branches == ["todo/abcd1234-0"]
    assert "todo/abcd1234-0" in branches(repo)


def test_t2433_what_is_not_a_live_worktree_is_left(world: Env) -> None:
    repo = make_repo(world)
    run = run_dir(world, "failed")
    (run / "wt-plain").mkdir()  # no .git
    gone = worktree(repo, run, "wt-gone", "todo/abcd1234-gone")
    sh(repo, "git", "worktree", "prune")
    (repo / ".git" / "worktrees" / "wt-gone" / "gitdir").unlink()
    detached = run / "wt-detached"
    sh(repo, "git", "worktree", "add", "-q", "--detach", str(detached), "origin/main")
    rep = reap.clean(run, apply=True)
    assert (run / "wt-plain").is_dir()
    assert gone.is_dir()
    assert not detached.exists()
    assert len(rep.skipped) == 2


@pytest.mark.parametrize("stage", ["implement", "spec", "shipping", "gate", "paused_retry"])
def test_t2433_a_working_run_is_never_touched(world: Env, stage: str) -> None:
    repo = make_repo(world)
    run = run_dir(world, stage)
    wt = worktree(repo, run, "wt", "todo/abcd1234-0")
    assert reap.clean(run, apply=True).refused == f"stage {stage}"
    assert wt.is_dir()


def test_t2433_a_run_with_a_live_process_a_turn_or_a_pending_file_is_refused(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = run_dir(world)
    monkeypatch.setattr(reap, "live_cwds", lambda: [run / "wt-x" / "sub"])
    assert reap.clean(run, apply=True).refused == "a live process works in it"
    monkeypatch.setattr(reap, "live_cwds", lambda: [world.root])
    (run / "inbox.json").write_text("[]", encoding="utf-8")
    assert reap.clean(run, apply=True).refused == "inbox.json waits"
    (run / "inbox.json").unlink()
    orphans.write(run, pid=1, start=orphans.start_of(1))
    assert reap.clean(run, apply=True).refused == "a turn is live"
    (run / "state.json").unlink()
    assert reap.clean(run, apply=True).refused == "no state"


def test_t2433_live_cwds_reads_proc(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    proc = tmp_path / "proc"
    for pid, target in (("1", tmp_path / "a"), ("2", None), ("self", tmp_path / "b")):
        (proc / pid).mkdir(parents=True)
        if target is not None:
            (proc / pid / "cwd").symlink_to(target)
    monkeypatch.setattr(reap, "PROC", proc)
    assert reap.live_cwds() == [tmp_path / "a"]
    monkeypatch.setattr(reap, "PROC", tmp_path / "missing")
    assert reap.live_cwds() == []


def test_t2433_a_repo_with_no_origin_keeps_the_branch_and_a_dry_run_keeps_venvs(world: Env) -> None:
    lone = world.tmp / "lone"
    lone.mkdir()
    sh(lone, "git", "init", "-q", "-b", "trunk")
    sh(lone, "git", "commit", "-q", "--allow-empty", "-m", "init")
    run = run_dir(world, "closed")
    sh(lone, "git", "worktree", "add", "-q", "-b", "todo/abcd1234-lone", str(run / "wt-lone"))
    (run / "node_modules").mkdir()
    rep = reap.clean(run, apply=False)
    assert rep.kept == ["todo/abcd1234-lone"]
    assert rep.payload == [str(run / "node_modules")]
    assert (run / "node_modules").is_dir()


def test_t2433_a_git_failure_skips_that_worktree(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(world)
    run = run_dir(world, "closed")
    wt = worktree(repo, run, "wt", "todo/abcd1234-0")

    def flaky(cwd: Path, *args: str, check: bool = True) -> object:
        if args[0] == "status":
            raise GitError("git status timed out", "run_failed")
        return git(cwd, *args, check=check)

    monkeypatch.setattr(reap, "git", flaky)
    rep = reap.clean(run, apply=True)
    assert rep.skipped == [f"{wt}: git status timed out"]
    assert wt.is_dir()
