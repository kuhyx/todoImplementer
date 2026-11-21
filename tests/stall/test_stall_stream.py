"""The stall clock reads the newest message or result line of the stream, not its last line (T2447, T2448).

2026-11-21: claude writes `system task_*` and `thinking_tokens` lines right after a tool result, so a result
that came 22 s after its call was never seen and a sharded test run in parallel calls looked quiet for 62 s
(`stall-job-test.sh`). Most `stall-model` episodes were an advisor call: a `server_tool_use` the advisor
model answers in 60-140 s, with nothing written meanwhile.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from todoimpl.runner import orphans
from todoimpl.stall import scan

STEM = "implement-1000.000"
CALL = "2026-11-21T11:00:00.000Z"
AT = 1795258800.0  # CALL as epoch seconds


def _stream(tmp_path: Path, *rows: object, mtime: float = 9e9) -> Path:
    run_dir = tmp_path / "dddddddd-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), "utf-8")
    os.utime(stream, (mtime, mtime))
    return run_dir


def _since(tmp_path: Path) -> list[float]:
    return [r.since for r in scan.running(tmp_path)]


def test_t2447_a_result_followed_by_system_lines_counts_at_its_own_time(tmp_path: Path) -> None:
    result = {"type": "user", "timestamp": CALL, "message": {"content": [{"type": "tool_result"}]}}
    _stream(
        tmp_path, result, {"type": "system", "subtype": "task_started"}, {"type": "system", "subtype": "x"}
    )
    assert _since(tmp_path) == [AT]


def test_t2447_torn_and_stream_event_lines_are_skipped(tmp_path: Path) -> None:
    _stream(tmp_path, {"type": "assistant", "timestamp": CALL}, {"type": "stream_event"}, "{half")
    assert _since(tmp_path) == [AT]


def test_t2447_a_bad_timestamp_or_none_far_back_is_no_output(tmp_path: Path) -> None:
    _stream(tmp_path, {"type": "assistant", "timestamp": "soon"}, {"type": "system"})
    assert _since(tmp_path) == [1000.0]


def test_t2448_a_pending_advisor_call_counts_as_work_for_its_grace(tmp_path: Path) -> None:
    call = {"type": "assistant", "timestamp": CALL, "message": {"content": [{"type": "server_tool_use"}]}}
    _stream(tmp_path, call)
    assert _since(tmp_path) == [AT + scan.ADVISOR]


def test_t2448_an_answered_advisor_call_is_plain_output(tmp_path: Path) -> None:
    done = {"type": "assistant", "timestamp": CALL, "message": {"content": [{"type": "advisor_tool_result"}]}}
    _stream(tmp_path, done)
    assert _since(tmp_path) == [AT]
