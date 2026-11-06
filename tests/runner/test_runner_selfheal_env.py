import os
import stat
from pathlib import Path

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import session


def test_t1209_claude_waits_for_background_subagents(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        assert {c["bg_wait"] for c in world.calls()} == {"0"}
    finally:
        sched.close()


def test_t1210_handoff_carries_the_self_check_and_the_live_report_tail(tmp_path: Path) -> None:
    rows = [{"criterion": "C1", "done": True, "note": "cat shows hi"}]
    text = session.handoff_summary(tmp_path, "last", rows, "x" * 2000 + "LIVE-END")
    assert "Self-check:\nC1: done - cat shows hi" in text
    live = text.split("Live check report (tail):\n")[1].split("\n\nLast reply:")[0]
    assert live.endswith("LIVE-END")
    assert len(live) <= 1500
    assert session.handoff_summary(tmp_path, "") == "No plan or reply was recorded yet."


def test_t1211_state_save_fsyncs_the_directory(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    kinds: list[bool] = []
    real = os.fsync

    def spy(fd: int) -> None:
        kinds.append(stat.S_ISDIR(os.fstat(fd).st_mode))
        real(fd)

    monkeypatch.setattr(os, "fsync", spy)
    store.save(tmp_path, RunState(task_id="abcd1234-0", stage="plan"))
    assert kinds == [False, True]
