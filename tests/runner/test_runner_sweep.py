"""The one-shot sweep of runs that already rest (T2433): dry run, apply, exclude, budget."""

from __future__ import annotations

import runpy
import sys
from itertools import chain, repeat
from typing import TYPE_CHECKING

import pytest
from runnerfakes import Env, make_repo, sh
from todoimpl.board import state as store
from todoimpl.runner import reap, sweep

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def run(world: Env, repo: Path, card: str, stage: str, *, commit: bool = False) -> Path:
    d = world.root / card
    d.mkdir(parents=True)
    store.save(d, store.RunState(task_id=card, stage=stage))
    sh(repo, "git", "worktree", "add", "-q", "-b", f"todo/{card}", str(d / "wt-x"), "origin/main")
    if commit:
        (d / "wt-x" / "f.txt").write_text("f\n", encoding="utf-8")
        sh(d / "wt-x", "git", "add", "-A")
        sh(d / "wt-x", "git", "commit", "-q", "-m", "f")
    return d


@pytest.fixture
def runs(world: Env, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    monkeypatch.setattr(reap, "live_cwds", list)
    repo = make_repo(world)
    found = {
        "shipped": run(world, repo, "aaaa0000-0", "shipped"),
        "failed": run(world, repo, "bbbb0000-0", "failed", commit=True),
        "live": run(world, repo, "cccc0000-0", "implement"),
        "excluded": run(world, repo, "dddd0000-0", "shipped"),
    }
    (world.root / "archive").mkdir()  # no state.json: not a run
    return found


def test_t2433_the_dry_run_lists_and_touches_nothing(
    world: Env, runs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    assert sweep.main(["--root", str(world.root), "--exclude", "dddd0000-0"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert f"would remove {runs['shipped'] / 'wt-x'}" in out
    assert f"would remove {runs['failed'] / 'wt-x'}" in out
    assert "would delete branch todo/aaaa0000-0 (aaaa0000-0)" in out
    assert "kept branch todo/bbbb0000-0 (bbbb0000-0): commits no remote has" in out
    assert not [line for line in out if "cccc0000" in line or "dddd0000" in line]
    assert out[-1] == "3 runs looked at"  # the excluded one is not looked at
    assert all((p / "wt-x").is_dir() for p in runs.values())


def test_t2433_apply_cleans_resting_runs_only(
    world: Env, runs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    (runs["shipped"] / "wt-plain").mkdir()
    (runs["failed"] / "done-manually.json").write_text("{}", encoding="utf-8")
    assert sweep.main(["--root", str(world.root), "--apply", "--exclude", "dddd0000-0"]) == 0
    out = capsys.readouterr().out
    assert not (runs["shipped"] / "wt-x").exists()
    assert (runs["failed"] / "wt-x").is_dir()
    assert "left bbbb0000-0: done-manually.json waits" in out
    assert f"skipped {runs['shipped'] / 'wt-plain'}: not a worktree" in out
    assert "deleted branch todo/aaaa0000-0" in out
    assert (runs["live"] / "wt-x").is_dir()
    assert (runs["excluded"] / "wt-x").is_dir()


def test_t2433_a_spent_budget_asks_for_another_call(
    world: Env, runs: dict[str, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    def clock(*ticks: float) -> Callable[[], float]:
        it = chain(ticks, repeat(99.0))
        return lambda: next(it)

    root = ["--root", str(world.root), "--apply", "--budget", "10"]
    assert sweep.main(root, clock=clock(0.0)) == sweep.AGAIN  # spent before the first worktree
    assert "budget spent after 0 of 4 runs: run it again" in capsys.readouterr().out
    assert (runs["shipped"] / "wt-x").is_dir()
    assert sweep.main(root, clock=clock(0.0, 0.0)) == sweep.AGAIN  # spent while that run was cleaned
    out = capsys.readouterr().out
    assert f"removed {runs['shipped'] / 'wt-x'}" in out
    assert "budget spent after 0 of 4 runs: run it again" in out
    assert (runs["failed"] / "wt-x").is_dir()


def test_t2433_the_module_runs_from_the_command_line(
    world: Env, runs: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_HOME", str(world.root))
    monkeypatch.setattr(sys, "argv", ["sweep"])
    sys.modules.pop("todoimpl.runner.sweep", None)
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("todoimpl.runner.sweep", run_name="__main__")
    assert stop.value.code == 0
