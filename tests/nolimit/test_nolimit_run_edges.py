"""A visit's other ends: read-only repos, a route that opens, a step cut at 60 s, git that fails."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from nolimitfakes import kuhy_repo, remote_log
from runnerfakes import Env, sh
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import fixes, repos, run, status, steps, worktree

NOW = 1_800_000_000.0


def load(world: Env, name: str = "demo") -> repos.Repo:
    found = repos.load(world.src / name)
    assert found is not None
    return found


def report(name: str) -> list[dict[str, object]]:
    found: list[dict[str, object]] = json.loads(
        (state_base() / "app-errors" / name).read_text(encoding="utf-8")
    )["errors"]
    return found


def test_a_read_only_repo_runs_its_lint_and_never_commits(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [("fix-demo", "echo x >> README.md")])
    kuhy_repo(world, "quiet")
    assert run.visit(load(world, "quiet"), NOW) == status.READONLY
    kuhy_repo(world, "linted", lint="echo lint >> README.md")
    assert run.visit(load(world, "linted"), NOW) == status.READONLY
    assert not worktree.dirty(worktree.Tree(worktree.home() / "linted", "x", "main"))
    kuhy_repo(world, "messy", lint="exit 1")
    assert run.visit(load(world, "messy"), NOW) == status.RED
    assert remote_log(world, "linted") == ["commands", "init"]


def test_t2546_the_visit_stops_the_moment_a_route_opens(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    assert run.visit(load(world), NOW, lambda: False) == status.STOPPED
    assert not (worktree.home() / "demo").exists()
    answers = iter([True, True])
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [("fix-a", "true"), ("fix-b", "true")])
    assert run.visit(load(world), NOW, lambda: next(answers, False)) == status.STOPPED
    assert remote_log(world) == ["commands", "init"]


def test_a_cut_step_files_a_slow_ticket_and_ends_the_visit(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    kuhy_repo(world, test="sleep 30")
    real = steps.run
    monkeypatch.setattr(steps, "run", lambda name, command, cwd: real(name, command, cwd, limit=1))
    assert run.visit(load(world), NOW) == status.SLOW
    [record] = report("slow-steps.json")
    assert (record["app"], record["repo"], record["signature"]) == ("demo", "kuhyx/demo", "slow-nolimit-gate")


def test_git_failing_is_a_red_ticket(world: Env) -> None:
    kuhy_repo(world, test="true")
    shutil.rmtree(world.tmp / "remotes" / "demo.git")
    assert run.visit(load(world), NOW) == status.RED
    [record] = report("nolimit.json")
    assert record["signature"] == "nolimit-git"


def test_the_worktree_is_remade_after_its_dir_went_and_old_branches_go(world: Env) -> None:
    checkout = kuhy_repo(world, test="true")
    repo = load(world)
    first = worktree.prepare(repo, NOW)
    (first.path / "stray.txt").write_text("x", encoding="utf-8")
    again = worktree.prepare(repo, NOW + 86_400)  # the next day: a new branch, the old one deleted
    assert not (again.path / "stray.txt").exists()
    refs = sh(checkout, "git", "for-each-ref", "--format=%(refname:short)", "refs/heads/nolimit/")
    assert refs.split() == [again.branch]
    shutil.rmtree(again.path)
    third = worktree.prepare(repo, NOW + 86_400)
    assert (third.path / "CLAUDE.md").is_file()


def test_the_default_branch_follows_origin_head(world: Env, tmp_path: Path) -> None:
    checkout = kuhy_repo(world, test="true")
    assert worktree.default_branch(checkout) == "main"
    sh(checkout, "git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")
    assert worktree.default_branch(checkout) == "main"
    sh(checkout, "git", "branch", "-q", "trunk")
    sh(checkout, "git", "push", "-q", "origin", "trunk")
    sh(checkout, "git", "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/trunk")
    assert worktree.default_branch(checkout) == "trunk"
