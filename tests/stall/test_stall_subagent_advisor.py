"""An advisor call a sub-agent waits on is work, wherever it sits in the stream (T2486).

2026-11-22, card 3f9de200-0: the main thread ended its turn (`result success`) while a background
sub-agent waited 124 s on an advisor call. The call sat 124 KB back and the newest message line was the
main thread's text, so the watch filed `stall-model` after 65 s.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from todoimpl.runner import orphans
from todoimpl.stall import advisor, scan

STEM = "implement-1000.000"
CALL = "2026-11-21T11:00:00.000Z"
AT = 1795258800.0  # CALL as epoch seconds
LATER = "2026-11-21T11:00:24.000Z"
SUB = "toolu_01SubAgentTask"


def _call(sid: str, at: str = CALL) -> dict[str, object]:
    content = [{"type": "server_tool_use", "id": sid, "name": "advisor", "input": {}}]
    return {"type": "assistant", "timestamp": at, "parent_tool_use_id": SUB, "message": {"content": content}}


def _answer(sid: str) -> dict[str, object]:
    content = [{"type": "advisor_tool_result", "tool_use_id": sid, "content": {}}]
    return {
        "type": "assistant",
        "timestamp": LATER,
        "parent_tool_use_id": SUB,
        "message": {"content": content},
    }


def _main_text() -> dict[str, object]:
    return {"type": "assistant", "timestamp": LATER, "message": {"content": [{"type": "text", "text": "x"}]}}


def _stream(tmp_path: Path, *rows: object) -> Path:
    run_dir = tmp_path / "dddddddd-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), "utf-8")
    os.utime(stream, (1.0, 1.0))
    return stream


def _filler(size: int) -> list[object]:
    """Main-thread work lines, `size` bytes or more, so the call falls out of the board's tail."""
    row = {"type": "system", "subtype": "task_progress", "pad": "p" * 1000}
    return [row] * (size // 1000 + 1)


def _since(tmp_path: Path) -> list[float]:
    return [r.since for r in scan.running(tmp_path)]


def test_t2486_a_sub_agents_pending_call_far_back_is_work(tmp_path: Path) -> None:
    _stream(tmp_path, _call("srvtoolu_A"), *_filler(130 * 1024), _main_text(), {"type": "result"})
    assert _since(tmp_path) == [AT + scan.ADVISOR]


def test_t2486_an_answered_call_adds_no_grace(tmp_path: Path) -> None:
    _stream(tmp_path, _call("srvtoolu_A"), *_filler(1024), _answer("srvtoolu_A"), _main_text())
    assert _since(tmp_path) == [AT + 24]


def test_t2486_the_latest_pending_call_sets_the_grace(tmp_path: Path) -> None:
    stream = _stream(tmp_path, _call("srvtoolu_A"), _call("srvtoolu_B", LATER), "{torn")
    assert advisor.pending_until(stream) == AT + 24 + scan.ADVISOR


def test_t2486_torn_stray_and_missing_lines_add_nothing(tmp_path: Path) -> None:
    block = {"type": "server_tool_use", "id": "srvtoolu_C"}
    no_time = {"type": "assistant", "message": {"content": [block]}}
    event = {"type": "stream_event", "event": {"content_block": block}}
    odd = {"type": "assistant", "message": "srvtoolu_E"}
    stream = _stream(tmp_path, '{"x": "srvtoolu_F', no_time, event, odd, '["srvtoolu_G"]')
    assert advisor.pending_until(stream) is None
    assert advisor.pending_until(tmp_path / "missing.jsonl") is None
