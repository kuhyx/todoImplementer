"""A tool result or a finished thinking block is real activity: the stall clock restarts on it (T2418).

A 50 s tool call and 15 s of thinking after its result were filed as a 65 s "waiting on the model" stall: only
tool calls and text reached events.jsonl. claude writes every result and assistant message to the turn's
stream file, so the time of its last such line counts too; its other lines (system, hooks) do not.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from todoimpl.runner import orphans
from todoimpl.stall import scan

STEM = "implement-1000.000"


def _turn(tmp_path: Path, last: object, at: float) -> Path:
    run_dir = tmp_path / "dddddddd-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text(json.dumps({"type": "assistant"}) + "\n" + json.dumps(last) + "\n", "utf-8")
    os.utime(stream, (at, at))
    return run_dir


@pytest.mark.parametrize("kind", ["user", "assistant"])
def test_t2418_a_result_or_message_line_in_the_stream_counts_as_activity(tmp_path: Path, kind: str) -> None:
    _turn(tmp_path, {"type": kind, "message": {"content": [{"type": "tool_result"}]}}, 5000.0)
    assert [r.since for r in scan.running(tmp_path)] == [5000.0]


@pytest.mark.parametrize("last", [{"type": "system", "subtype": "hook"}, "{half", [1]])
def test_t2418_other_stream_lines_do_not(tmp_path: Path, last: object) -> None:
    run_dir = _turn(tmp_path, last, 5000.0)
    if last == "{half":
        (run_dir / f"{STEM}.stream.jsonl").write_text('{"type": "user"}\n{half', "utf-8")
        os.utime(run_dir / f"{STEM}.stream.jsonl", (5000.0, 5000.0))
    assert [r.since for r in scan.running(tmp_path)] == [1000.0]  # the turn's start only


def test_t2418_no_stream_file_is_no_output(tmp_path: Path) -> None:
    assert scan.last_output(tmp_path, STEM) is None
