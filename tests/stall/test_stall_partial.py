"""claude streams partial messages, so a long answer writes lines while the model works (T2452).

Without `--include-partial-messages` claude wrote nothing while the model wrote one long message, and a 60 s
answer read as a `stall-model`. The `stream_event` lines are liveness only: they make no activity, no cost
and no context reading, so the card's page and its counts stay as they were.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from todoimpl.credits.meter import Meter
from todoimpl.runner import orphans
from todoimpl.runner.stream import StreamParser
from todoimpl.stall import scan

STEM = "implement-1000.000"
DELTA = {
    "type": "stream_event",
    "session_id": "s1",
    "parent_tool_use_id": None,
    "event": {
        "type": "message_start",
        "message": {"id": "m1", "model": "claude-opus-5-5", "usage": {"input_tokens": 9, "output_tokens": 1}},
    },
}


def test_t2452_a_trailing_stream_event_counts_at_the_files_time(tmp_path: Path) -> None:
    run_dir = tmp_path / "dddddddd-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text(json.dumps({"type": "system"}) + "\n" + json.dumps(DELTA) + "\n", "utf-8")
    os.utime(stream, (5000.0, 5000.0))
    assert [r.since for r in scan.running(tmp_path)] == [5000.0]


def test_t2452_stream_events_make_no_activity_cost_or_context() -> None:
    parser = StreamParser()
    seen: list[int] = []
    parser.on_context = seen.append
    assert parser.feed(json.dumps(DELTA) + "\n") == []
    assert seen == []
    assert parser.result.context_tokens == 0
    assert Meter().feed(DELTA) is False


def test_t2469_a_trailing_thinking_tokens_line_counts_at_the_files_time(tmp_path: Path) -> None:
    # 2026-11-21 stream of f2199a40-0: while the model thinks, claude interleaves `system thinking_tokens`
    # lines with the `thinking_delta` events, so the last line is often a system line and the walk fell
    # back to the tool result before the thinking: a 90 s think read as a 90 s quiet
    run_dir = tmp_path / "dddddddd-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    rows = [
        {"type": "user", "timestamp": "2026-11-21T16:00:00+00:00", "message": {"content": []}},
        {"type": "system", "subtype": "status", "status": "requesting"},
        DELTA,
        {"type": "system", "subtype": "thinking_tokens", "estimated_tokens": 185},
    ]
    stream.write_text("".join(json.dumps(row) + "\n" for row in rows), "utf-8")
    os.utime(stream, (1795280000.0, 1795280000.0))
    assert [r.since for r in scan.running(tmp_path)] == [1795280000.0]
