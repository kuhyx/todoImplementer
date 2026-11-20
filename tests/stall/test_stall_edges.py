"""Edges of the stall watch: unreadable files, dead turns, the thread, and the board wiring (T2402)."""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path

from todoimpl.runner import orphans
from todoimpl.stall import report, scan
from todoimpl.stall.watch import StallWatch


def test_t2402_last_activity_skips_what_is_not_a_timed_session_event(tmp_path: Path) -> None:
    events = tmp_path / scan.EVENTS
    assert scan.last_activity(events) is None  # no file
    rows = [
        {"type": "activity", "at": 5.0, "kind": "tool"},
        {"type": "activity", "at": True, "kind": "tool"},
        {"type": "activity", "kind": "text"},
        {"type": "tool", "at": 9.0},
        [1, 2],
    ]
    events.write_text("\n".join(json.dumps(r) for r in rows) + "\n{half", "utf-8")
    assert scan.last_activity(events) == 5.0
    events.write_text(json.dumps({"type": "activity", "at": 7.0, "kind": "system"}) + "\n", "utf-8")
    assert scan.last_activity(events) is None  # only board lines: no real activity
    events.write_text(json.dumps({"type": "activity", "at": 3.0, "kind": "tool"}) + "\n" + "x" * 100, "utf-8")
    assert scan.last_activity(events, tail=50) is None  # the tail window holds no whole activity line
    assert scan.last_activity(events) == 3.0


def test_t2402_dead_turns_and_turns_with_no_time_are_not_running(tmp_path: Path) -> None:
    assert scan.running(tmp_path / "missing") == []
    dead = tmp_path / "aaaaaaaa-0"
    dead.mkdir()
    orphans.write(dead, stem="implement-1.0", pid=os.getpid(), start="0")  # pid reused: not our claude
    no_pid = tmp_path / "bbbbbbbb-0"
    no_pid.mkdir()
    orphans.write(no_pid, stem="implement-1.0")
    untimed = tmp_path / "cccccccc-0"
    untimed.mkdir()
    orphans.write(untimed, stem="plan", pid=os.getpid(), start=orphans.start_of(os.getpid()))
    assert scan.running(tmp_path) == []


def test_t2402_a_broken_open_file_is_no_open_episode(tmp_path: Path) -> None:
    (tmp_path / report.OPEN).write_text('["x"]', "utf-8")
    assert report.open_episodes(tmp_path) == {}
    (tmp_path / report.OPEN).write_text('{"a": 1, "b": "x", "c": true}', "utf-8")
    assert report.open_episodes(tmp_path) == {"a": 1.0}


def test_t2402_a_broken_report_is_started_again(tmp_path: Path) -> None:
    report.path().parent.mkdir(parents=True, exist_ok=True)
    report.path().write_text('["x"]', "utf-8")
    report.file("stall-model", "d", 0.0)
    (record,) = json.loads(report.path().read_text("utf-8"))["errors"]
    assert (record["signature"], record["count"]) == ("stall-model", 1)


def test_t2402_the_thread_ticks_until_stopped_and_survives_a_failing_tick(tmp_path: Path) -> None:
    ticks: list[int] = []
    done = threading.Event()

    class Failing(StallWatch):
        def tick(self) -> None:
            ticks.append(1)
            if len(ticks) == 2:
                done.set()
            raise RuntimeError

    watch = Failing(tmp_path, interval=0.01)
    watch.start()
    assert done.wait(5)
    watch.stop()
    assert len(ticks) >= 2
