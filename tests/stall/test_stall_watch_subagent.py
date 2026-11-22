"""The whole watch tick does not file `stall-model` for the 3f9de200-0 episode shape (T2504).

2026-11-22, card 3f9de200-0: the main thread ended its turn (`result success`) while a
background sub-agent waited 124 s on an advisor call. The call sat 124 KB back and the
newest message line was the main thread's text, so the watch filed `stall-model` after 65 s.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from todoimpl.runner import orphans
from todoimpl.stall import report, scan
from todoimpl.stall.watch import LIMIT, StallWatch

STEM = "implement-1000.000"
CALL = "2026-11-21T11:00:00.000Z"
AT = 1795258800.0  # CALL as epoch seconds
LATER = "2026-11-21T11:00:24.000Z"
SUB = "toolu_01SubAgentTask"


def _call(sid: str, at: str = CALL) -> dict[str, object]:
    content = [{"type": "server_tool_use", "id": sid, "name": "advisor", "input": {}}]
    return {"type": "assistant", "timestamp": at, "parent_tool_use_id": SUB, "message": {"content": content}}


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


def _model(_run: scan.Running) -> tuple[str, str]:
    return ("stall-model", "d")


def test_t2504_a_sub_agents_pending_advisor_call_files_no_stall(tmp_path: Path) -> None:
    _stream(tmp_path, _call("srvtoolu_A"), *_filler(130 * 1024), _main_text(), {"type": "result"})
    filed: list[str] = []

    def _diag_filed(_run: scan.Running) -> tuple[str, str]:
        filed.append("x")
        return _model(_run)

    def _clock() -> float:
        # Main text at AT+24; LIMIT=60; advisor window=240. At AT+24+60+5=89s we are
        # past the 60s quiet limit but still inside the 240s advisor window.
        return AT + 24 + LIMIT + 5

    watch = StallWatch(tmp_path, clock=_clock, diagnose=_diag_filed)
    watch.tick()
    assert filed == []
    assert not (tmp_path / report.LOG).exists()


def test_t2504_once_the_advisor_window_ends_the_quiet_is_filed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stream(tmp_path, _call("srvtoolu_A"), *_filler(130 * 1024), _main_text(), {"type": "result"})
    sent: list[str] = []
    monkeypatch.setattr(report, "file", lambda signature, *_a, **_k: sent.append(signature))

    def _clock() -> float:
        return AT + scan.ADVISOR + LIMIT + 5

    watch = StallWatch(tmp_path, clock=_clock, diagnose=_model)
    watch.tick()
    assert sent == ["stall-model"]
