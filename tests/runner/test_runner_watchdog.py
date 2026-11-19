"""A silent card names its wait and age; past 5 min a dead wait is killed and the session told (T2198)."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest
from adoptfakes import STEM, go, line, rig, text
from todoimpl.board import state as store
from todoimpl.board.card import current_line
from todoimpl.board.state import RunState
from todoimpl.board.status import SILENT, Status
from todoimpl.runner import adopt, deadwait, orphans, watchdog
from todoimpl.runner.files import read_json
from todoimpl.runner.stream import StreamParser
from todoimpl.runner.turn import TurnEnv, run_turn

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

BEAT = line({"type": "tool_progress", "tool_name": "Bash", "elapsed_time_seconds": 30, "heartbeat": True})
LOOP = "while pgrep -f deployhost; do sleep 5; done"
DEAD = deadwait.Verdict(deadwait.DEAD, "pgrep-self", LOOP, deadwait.Job(101, (101,), (1.0,)), "deployhost")


def _until(check: Any, limit: float = 5.0) -> None:
    deadline = time.monotonic() + limit
    while not check() and time.monotonic() < deadline:
        time.sleep(0.02)


@pytest.mark.parametrize(
    ("raw", "real"),
    [
        (BEAT, False),
        (line({"type": "rate_limit_event"}), False),
        (b"", False),
        (b"not json", True),
        (text("hi"), True),
        (line({"type": "user", "message": {}}), True),
        (line({"type": "system", "subtype": "thinking_tokens"}), True),
    ],
)
def test_t2198_a_tool_progress_heartbeat_is_no_real_action(raw: bytes, real: bool) -> None:
    assert watchdog.real(raw.rstrip(b"\n")) is real


def test_t2198_only_a_real_action_moves_the_clock_and_clears_the_shown_silence(tmp_path: Path) -> None:
    shown: list[Any] = []
    now = [5000.0]
    watch = watchdog.Watch(tmp_path, STEM, shown.append, lambda *_a: None, clock=lambda: now[0])
    assert watch.since == 5000.0
    assert read_json(tmp_path / f"{STEM}{watchdog.REAL_SUFFIX}") == 5000.0
    watch.shown = {"since": 1.0}
    now[0] = 5100.0
    watch.heard([BEAT.rstrip(b"\n")])
    assert (watch.since, shown) == (5000.0, [])
    watch.heard([text("back").rstrip(b"\n")])
    assert (watch.since, shown) == (5100.0, [None])
    assert watchdog.Watch(tmp_path, STEM, shown.append, lambda *_a: None).since == 5100.0


def test_t2198_a_dead_wait_silent_past_5_min_is_killed_once_and_the_session_gets_a_note(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    stream = tmp_path / f"{STEM}.stream.jsonl"
    stream.write_bytes(text("waiting for the deploy") + BEAT)
    (tmp_path / f"{STEM}.fed").write_text(str(len(stream.read_bytes())))  # shown before a restart
    (tmp_path / f"{STEM}{watchdog.REAL_SUFFIX}").write_text(str(time.time() - 400))
    me = os.getpid()
    rec = orphans.Record(stem=STEM, role="implement", pid=me, host_pid=me, host_start=orphans.start_of(me))
    stopped: list[tuple[deadwait.Verdict, str]] = []
    monkeypatch.setattr(watchdog, "LOOK_EVERY", 0.02)
    monkeypatch.setattr(deadwait.Judge, "look", lambda _self, _pid: [DEAD])
    monkeypatch.setattr(deadwait, "stop", lambda v, note: stopped.append((v, note)))
    shown: list[Any] = []
    events: list[tuple[str, str]] = []

    def later() -> None:
        _until(lambda: len(shown) >= 1 and stopped)
        time.sleep(0.1)  # more looks: the same job is never killed twice
        with stream.open("ab") as out:
            out.write(BEAT)  # a heartbeat does not end the silence
        time.sleep(0.05)
        (tmp_path / f"{STEM}.exit.json").write_text('{"code": 0}')

    threading.Thread(target=later).start()
    watch = watchdog.Watch(
        tmp_path, STEM, shown.append, lambda kind, msg, _tool=None: events.append((kind, msg))
    )
    code = adopt.follow(tmp_path, rec, StreamParser(), lambda *_a: None, threading.Event(), watch=watch)
    assert code == 0
    assert len(stopped) == 1
    assert shown[0] is not None
    assert (shown[0]["verdict"], shown[0]["rule"], shown[0]["who"], shown[0]["min"]) == (
        "dead",
        "pgrep-self",
        LOOP,
        6,
    )
    note = json.loads((tmp_path / "inbox.json").read_text())[0]
    assert note == stopped[0][1].strip()
    assert note.startswith("(runner)")
    assert "pgrep -f" in note
    assert LOOP in note
    assert events == [("error", note)]


def test_t2198_a_silent_turn_saves_and_announces_its_silence_and_ends_without_it(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run_dir, wt = rig(world, tmp_path)
    monkeypatch.setattr(adopt, "IDLE_AFTER_RESULT", 1.0)
    monkeypatch.setattr(watchdog, "SUSPICIOUS", 0.05)
    monkeypatch.setattr(watchdog, "LOOK_EVERY", 0.05)
    monkeypatch.setattr(deadwait.Judge, "look", lambda _self, _pid: [])
    world.script("abcd1234", {"_fake": "result", "text": "R: gate running"}, {"_fake": "sleep", "sec": 30})
    st = RunState(task_id="abcd1234-0", stage="implement", extra={SILENT: {"since": 1.0}})
    shown: list[Any] = []

    def publish(event: dict[str, Any]) -> None:
        if event["type"] == "stage":
            on_disk = store.load(run_dir)
            shown.append(on_disk.extra.get(SILENT) if on_disk else None)

    env = TurnEnv(run_dir, wt, publish, lambda _h: None, lambda: 100.0)
    assert run_turn(env, st, "implement", go).tag == "R"
    assert any(isinstance(s, dict) and s.get("verdict") == "unknown" for s in shown)
    assert SILENT not in st.extra


NOW = 1_800_000_000.0


@pytest.mark.parametrize(
    ("silence", "line_"),
    [
        ({"since": NOW - 30, "verdict": "unknown", "who": "bash x.sh"}, "implement"),
        ({"since": NOW - 130, "verdict": "unknown", "who": "bash x.sh"}, "⏳ bash x.sh 2m"),
        ({"since": NOW - 130, "verdict": "unknown", "who": ""}, "implement 2m"),
        ({"since": NOW - 400, "verdict": "unknown", "who": "bash x.sh"}, "🚨 ⏳ bash x.sh 6m"),
        ({"since": NOW - 400, "verdict": "healthy", "who": "make test"}, "⏳ make test 6m"),
        ({"since": NOW - 400, "verdict": "dead", "who": LOOP}, f"💀 ⏳ {LOOP} 6m"),
        ("garbage", "implement"),
    ],
)
def test_t2198_the_card_line_names_a_silent_wait_its_age_and_marks_it_past_5_min(
    silence: Any,
    line_: str,
) -> None:
    run = RunState(task_id="e1fa3e99-0", stage="implement", extra={SILENT: silence})
    assert current_line(Status.WORKING, run, None, NOW) == line_


def test_t2198_a_silent_lock_wait_keeps_its_holder_and_gains_its_age() -> None:
    wait = {"lock": True, "who": "d4ce7675-0", "since": None}
    run = RunState(
        task_id="e1fa3e99-0",
        stage="implement",
        extra={"waits_for": wait, SILENT: {"since": NOW - 400, "verdict": "healthy", "who": "x"}},
    )
    assert current_line(Status.WORKING, run, None, NOW) == "⏳🔒 d4ce7675-0 6m"
