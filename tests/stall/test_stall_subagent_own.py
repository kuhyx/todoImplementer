"""A foreground sub-agent's own work counts, though claude never copies it to the turn's stream (T2561).

2026-11-27, card a0783cdb-0: a `web-fetch` sub-agent got its last fetch result at 10:09:12, thought 27 s,
called the advisor (answered 71 s later), thought again and wrote its report, and returned at 10:11:32.
The turn's stream got only `tool_progress` heartbeats meanwhile: claude copies a sub-agent's tool calls
and results to it, not its thinking, advisor call or text. The watch filed `stall-model` at 68 s. The
sub-agent's own transcript (`~/.claude/projects/<cwd>/<session>/subagents/agent-*.jsonl`) holds them,
appended as they come.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from todoimpl.runner import orphans
from todoimpl.stall import report, scan, subagent
from todoimpl.stall.watch import LIMIT, StallWatch

if TYPE_CHECKING:
    from pathlib import Path

STEM = "spec-1000.000"
SID = "f849c58f-7643-4a19-92f1-03cb4fe388de"
CWD = "/w/.cache/a0783cdb-0/wt_x"
SLUG = "-w--cache-a0783cdb-0-wt-x"
FETCHED = "2026-11-27T10:09:12.209Z"
AT = datetime.fromisoformat(FETCHED).timestamp()
SUB = "toolu_01Agent"


def _iso(offset: float) -> str:
    return datetime.fromtimestamp(AT + offset).astimezone().isoformat()


def _line(kind: str, offset: float, block: dict[str, object]) -> dict[str, object]:
    return {"type": kind, "timestamp": _iso(offset), "message": {"content": [block]}}


def _heartbeat(n: int) -> dict[str, object]:
    return {"type": "tool_progress", "tool_use_id": f"{SUB}-heartbeat-{n}", "parent_tool_use_id": SUB}


def _card(tmp_path: Path, *, init: bool = True) -> Path:
    run_dir = tmp_path / "aaaaaaaa-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    fetched = {
        **_line("user", 0, {"type": "tool_result", "tool_use_id": "toolu_f"}),
        "parent_tool_use_id": SUB,
    }
    rows = [fetched, _heartbeat(3), _heartbeat(4)]
    if init:
        rows.insert(0, {"type": "system", "subtype": "init", "cwd": CWD, "session_id": SID})
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    os.utime(stream, (1.0, 1.0))
    return run_dir


def _transcript(*rows: dict[str, object], name: str = "agent-a1") -> Path:
    path = subagent.PROJECTS / SLUG / SID / "subagents" / f"{name}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    return path


THOUGHT = _line("assistant", 27.1, {"type": "thinking", "thinking": "t"})
CALL = _line("assistant", 27.1, {"type": "server_tool_use", "id": "srvtoolu_1", "name": "advisor"})
ANSWER = _line("assistant", 98.6, {"type": "advisor_tool_result", "tool_use_id": "srvtoolu_1"})


def test_t2561_a_sub_agents_advisor_call_is_the_cards_work(tmp_path: Path) -> None:
    _card(tmp_path)
    _transcript(THOUGHT, CALL, {"type": "api-request"})
    assert [r.since for r in scan.running(tmp_path)] == [pytest.approx(AT + 27.1 + scan.ADVISOR)]
    _transcript(THOUGHT, CALL, ANSWER)
    assert [r.since for r in scan.running(tmp_path)] == [pytest.approx(AT + 98.6)]


def test_t2561_the_watch_files_no_stall_while_the_sub_agent_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _card(tmp_path)
    _transcript(THOUGHT, CALL)
    sent: list[str] = []
    monkeypatch.setattr(report, "file", lambda signature, *_a, **_k: sent.append(signature))
    StallWatch(tmp_path, clock=lambda: AT + 68, diagnose=lambda _r: ("stall-model", "d")).tick()
    assert sent == []
    _transcript(THOUGHT, CALL, ANSWER)
    StallWatch(tmp_path, clock=lambda: AT + 98.6 + LIMIT + 5, diagnose=lambda _r: ("stall-model", "d")).tick()
    assert sent == ["stall-model"]  # a sub-agent quiet for over a minute is still a stall


def test_t2561_transcripts_older_than_the_turn_do_not_count(tmp_path: Path) -> None:
    _card(tmp_path)
    old = _transcript(_line("assistant", 500, {"type": "text", "text": "x"}), name="agent-old")
    os.utime(old, (999.0, 999.0))  # written before the turn started at 1000
    assert [r.since for r in scan.running(tmp_path)] == [AT]


def test_t2561_a_stream_with_no_session_reads_no_transcript(tmp_path: Path) -> None:
    run_dir = _card(tmp_path, init=False)
    _transcript(THOUGHT)
    stream = run_dir / f"{STEM}.stream.jsonl"
    assert subagent.until(stream, 0.0) is None
    stream.write_text(json.dumps({"type": "system", "subtype": "init", "cwd": CWD}) + "\n", "utf-8")
    assert subagent.until(stream, 0.0) is None
    stream.write_text('{"type": "system", "subtype": "init", "cwd": "/w/a", "session_id": "s"', "utf-8")
    assert subagent.until(stream, 0.0) is None  # a torn first line
    assert subagent.until(run_dir / "gone.stream.jsonl", 0.0) is None
    stream.write_text('[1]\n{"type": "system", "subtype": "status"}\n', "utf-8")
    assert subagent.until(stream, 0.0) is None  # no init line at all


def test_t2561_an_init_line_after_a_dev_intent_line_is_found(tmp_path: Path) -> None:
    run_dir = _card(tmp_path)
    stream = run_dir / f"{STEM}.stream.jsonl"
    intent = {"type": "system", "subtype": "dev_intent", "kind": "android_app", "session_id": SID}
    stream.write_text(json.dumps(intent) + "\n" + stream.read_text("utf-8"), "utf-8")
    _transcript(THOUGHT)
    assert subagent.until(stream, 0.0) == pytest.approx(AT + 27.1)


def test_t2561_a_transcript_that_vanished_is_skipped(tmp_path: Path) -> None:
    run_dir = _card(tmp_path)
    gone = _transcript(THOUGHT).with_name("agent-gone.jsonl")
    gone.symlink_to(tmp_path / "nowhere")  # listed by the glob, then gone when read
    assert subagent.until(run_dir / f"{STEM}.stream.jsonl", 0.0) == pytest.approx(AT + 27.1)
    _transcript({"type": "api-request"})  # a sub-agent that has written no message yet
    assert subagent.until(run_dir / f"{STEM}.stream.jsonl", 0.0) is None
