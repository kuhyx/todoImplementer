"""The follower puts an idle turn's wait on its card and takes it off again (T2124)."""

from __future__ import annotations

import os
import threading
import time
from typing import TYPE_CHECKING, Any

from adoptfakes import STEM, go, result, rig, text
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.board.status import WAITS_FOR
from todoimpl.runner import adopt, bgwait, orphans
from todoimpl.runner.stream import StreamParser
from todoimpl.runner.turn import TurnEnv, run_turn

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from runnerfakes import Env

WAIT = {"lock": True, "who": "d4ce7675-0", "since": 1.0}


def _until(check: Any, limit: float = 5.0) -> None:
    deadline = time.monotonic() + limit
    while not check() and time.monotonic() < deadline:
        time.sleep(0.02)


def test_t2124_the_wait_shows_once_after_the_result_and_clears_when_the_stream_speaks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = tmp_path / f"{STEM}.stream.jsonl"
    stream.write_bytes(text("starting the gate") + result("R: gate running"))
    me = os.getpid()
    rec = orphans.Record(stem=STEM, role="implement", pid=me, host_pid=me, host_start=orphans.start_of(me))
    found: list[dict[str, Any] | None] = [WAIT]
    scans: list[int | None] = []

    def scan(pid: int | None, _run_dir: Path, _lock: Path) -> dict[str, Any] | None:
        scans.append(pid)
        return found[0]

    monkeypatch.setattr(bgwait, "scan", scan)
    monkeypatch.setattr(adopt, "WAIT_AFTER", 0.05)
    monkeypatch.setattr(adopt, "SCAN_EVERY", 0.05)
    seen: list[dict[str, Any] | None] = []

    def later() -> None:
        _until(lambda: len(scans) >= 3)  # scanned again and again, shown once
        found[0] = None
        with stream.open("ab") as out:
            out.write(text("the notice came"))
        _until(lambda: len(seen) >= 2)
        files_exit = tmp_path / f"{STEM}.exit.json"
        files_exit.write_text('{"code": 0}')

    threading.Thread(target=later).start()
    code = adopt.follow(
        tmp_path, rec, StreamParser(), lambda *_a: None, threading.Event(), waiting=seen.append
    )
    assert code == 0
    assert seen == [WAIT, None]
    assert set(scans) == {me}


def test_t2124_a_turn_saves_and_announces_its_wait_and_ends_without_it(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 1.0)
    monkeypatch.setattr(adopt, "WAIT_AFTER", 0.05)
    monkeypatch.setattr(bgwait, "scan", lambda *_a: WAIT)
    world.script("abcd1234", {"_fake": "result", "text": "R: gate running"}, {"_fake": "sleep", "sec": 30})
    st = RunState(task_id="abcd1234-0", stage="implement", extra={WAITS_FOR: {"who": "stale"}})
    shown: list[tuple[Any, Any]] = []

    def publish(event: dict[str, Any]) -> None:
        if event["type"] == "stage":
            on_disk = store.load(run_dir)
            shown.append((st.extra.get(WAITS_FOR), on_disk.extra.get(WAITS_FOR) if on_disk else None))

    env = TurnEnv(run_dir, wt, publish, lambda _h: None, lambda: 100.0)
    res = run_turn(env, st, "implement", go)
    assert res.tag == "R"
    assert (WAIT, WAIT) in shown  # saved before the page hears of it
    assert WAITS_FOR not in st.extra
    on_disk = store.load(run_dir)
    assert on_disk is not None
    assert WAITS_FOR not in on_disk.extra  # a stale wait (a restart) never outlives the turn
