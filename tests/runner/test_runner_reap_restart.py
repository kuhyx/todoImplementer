"""A Restart right after Cancel waits for the cancelled run's reap before it drives (T2443)."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait, wait_stage
from todoimpl.runner import reap

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from runnerfakes import Env


def test_t2443_a_restart_waits_for_the_cancelled_runs_reap(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    entered, release = threading.Event(), threading.Event()
    original = reap._worktree

    def slow(wt: Path, rep: reap.Report, *, apply: bool) -> None:  # a removal still running on a busy disk
        entered.set()
        release.wait(10)
        original(wt, rep, apply=apply)

    monkeypatch.setattr(reap, "_worktree", slow)
    sched, _ = boot(world, PLAN, ({"_fake": "sleep", "sec": 20},), done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: any("Implement" in c["prompt"] for c in world.calls()))
        sched.cancel(CARD)
        wait_stage(world, sched, "cancelled")
        assert entered.wait(10)
        before = len(world.calls())
        for turn in (PLAN, IMPL, LIVE_OK):
            world.script("abcd1234", *turn)
        sched.start(CARD)
        time.sleep(1.0)  # a drive that did not wait would have sent its first turn by now
        assert len(world.calls()) == before
        release.set()
        wait_stage(world, sched, "gate", turns=3)
    finally:
        release.set()
        sched.close()


def test_t2443_settle_returns_at_once_when_no_reap_runs() -> None:
    started = time.monotonic()
    reap.settle("nothing-0")
    assert time.monotonic() - started < 1
