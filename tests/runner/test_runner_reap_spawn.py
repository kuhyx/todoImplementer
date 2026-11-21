"""The reaper's thread (T2433): only resting runs, one at a time, never across a new Start, Close too."""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any

import pytest
from runnerfakes import Env, FakeClient, make_repo, sh, task
from schedfakes import CARD, reply, wait_stage
from todoimpl.board import state as store
from todoimpl.runner import reap
from todoimpl.runner.scheduler import Scheduler


class Sched:
    """The Scheduler parts the reaper reads."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._cv = threading.Condition()
        self._active: set[str] = set()
        self._queue: list[str] = []


def rest(root: Path, stage: str) -> Path:
    run = root / CARD
    run.mkdir(parents=True, exist_ok=True)
    store.save(run, store.RunState(task_id=CARD, stage=stage))
    return run


def test_t2433_spawn_skips_a_working_run_and_a_card_already_being_cleaned(tmp_path: Path) -> None:
    sched: Any = Sched(tmp_path)
    assert reap.spawn(sched, CARD) is None  # no run
    rest(tmp_path, "implement")
    assert reap.spawn(sched, CARD) is None
    rest(tmp_path, "shipped")
    reap._cleaning.add(CARD)
    try:
        assert reap.spawn(sched, CARD) is None
    finally:
        reap._cleaning.discard(CARD)


def test_t2433_a_card_started_again_is_left_alone(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reap, "live_cwds", list)
    repo = make_repo(world)
    run = rest(world.root, "cancelled")
    sh(repo, "git", "worktree", "add", "-q", "-b", "todo/x", str(run / "wt"), "origin/main")
    sched: Any = Sched(world.root)
    sched._queue.append(CARD)  # kuhy pressed Restart right after the Cancel
    thread = reap.spawn(sched, CARD)
    assert thread is not None
    thread.join(20)
    assert (run / "wt").is_dir()
    assert CARD not in reap._cleaning


def test_t2433_a_failing_clean_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(*_: object, **__: object) -> reap.Report:
        raise OSError("disk")

    monkeypatch.setattr(reap, "clean", boom)
    rest(tmp_path, "closed")
    thread = reap.spawn(Sched(tmp_path), CARD)  # type: ignore[arg-type]
    assert thread is not None
    thread.join(20)
    assert "reap abcd1234-0 failed" in caplog.text
    assert CARD not in reap._cleaning


def test_t2433_close_frees_the_run_too(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []
    monkeypatch.setattr(reap, "spawn", lambda _sched, card: seen.append(card))
    make_repo(world)
    world.script("demo", *reply("C1: marker exists\n\nD: confirmed"))
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        assert sched.auto_start(CARD, 1.0)
        wait_stage(world, sched, "gate", tag="D")
        seen.clear()
        sched.close_item(CARD)
        assert seen == [CARD]
    finally:
        sched.close()


def test_t2433_summary_names_what_was_done(tmp_path: Path) -> None:
    assert reap.summary(reap.Report(tmp_path / "r", refused="stage gate")) == "r: left (stage gate)"
    rep = reap.Report(tmp_path / "r", removed=["a"], kept=["todo/x"])
    assert reap.summary(rep) == "r: 1 worktrees, 0 branches deleted, 1 kept, 0 venvs, 0 skipped []"
