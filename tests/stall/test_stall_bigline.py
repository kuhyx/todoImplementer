"""One stream line bigger than the board's tail hid the turn's newest output (T2560).

2026-11-27, card bcf6a474-0: a tool result at 10:14:39 was followed by claude's `system commands_changed`
line (the skill list, 73,501 bytes). The board read the stream's last 64 KB, which then held only that cut
line, so `last_output` found no message line and the watch measured from the tool call 35 s earlier: it filed
`stall-model` at 68 s, 33 s after the model was asked. Both readers now read further back (`stall/output.py`).
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from todoimpl.runner import orphans
from todoimpl.stall import output, report, scan
from todoimpl.stall.watch import LIMIT, StallWatch

if TYPE_CHECKING:
    from pathlib import Path

STEM = "live_check-1000.000"
RESULT = "2026-11-27T10:14:39.900Z"
AT = datetime.fromisoformat(RESULT).timestamp()
SIZES = [output.BOARD_TAIL + 1, 73_501, 5 * output.BOARD_TAIL]  # one growth step, the real line, two steps


def _result() -> dict[str, object]:
    content = [{"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}]
    return {"type": "user", "timestamp": RESULT, "message": {"content": content}}


def _text() -> dict[str, object]:
    return {"type": "assistant", "timestamp": RESULT, "message": {"content": [{"type": "text", "text": "x"}]}}


def _skills(size: int) -> dict[str, object]:
    """Return a `commands_changed` line of `size` bytes or a little more."""
    return {"type": "system", "subtype": "commands_changed", "commands": "c" * size}


def _write(run_dir: Path, *rows: object) -> Path:
    run_dir.mkdir(exist_ok=True)
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_bytes(
        b"".join((r if isinstance(r, bytes) else json.dumps(r).encode()) + b"\n" for r in rows)
    )
    os.utime(stream, (1.0, 1.0))
    return stream


@pytest.mark.parametrize("size", SIZES)
def test_t2560_a_line_past_the_tail_hides_no_output(tmp_path: Path, size: int) -> None:
    _write(
        tmp_path, _result(), _skills(size), {"type": "system", "subtype": "status", "status": "requesting"}
    )
    assert scan.last_output(tmp_path, STEM) == AT


@pytest.mark.parametrize("size", SIZES)
def test_t2560_a_line_past_the_tail_hides_no_ended_turn(tmp_path: Path, size: int) -> None:
    _write(tmp_path, _text(), {"type": "result"}, _skills(size))
    assert scan.turn_over(tmp_path, STEM) is True
    _write(tmp_path, {"type": "result"}, _text(), _skills(size))
    assert scan.turn_over(tmp_path, STEM) is False


def test_t2560_past_the_cap_there_is_no_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(output, "CAP", 4 * output.BOARD_TAIL)
    _write(tmp_path, _result(), _skills(5 * output.BOARD_TAIL))
    assert scan.last_output(tmp_path, STEM) is None
    assert scan.turn_over(tmp_path, STEM) is False


def test_t2560_a_tail_that_starts_on_a_line_keeps_that_line(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(output, "CAP", output.BOARD_TAIL)  # no second read: the first must keep the line
    line = json.dumps(_result()).encode()
    pad = json.dumps({"type": "system", "pad": ""}).encode()
    filler = b"x" * (output.BOARD_TAIL - len(line) - len(pad) - 2)
    pad = json.dumps({"type": "system", "pad": filler.decode()}).encode()
    stream = _write(tmp_path, b"cut", line, pad)
    assert stream.stat().st_size - output.BOARD_TAIL == len(b"cut\n")
    assert scan.last_output(tmp_path, STEM) == AT


def _model(_run: scan.Running) -> tuple[str, str]:
    return ("stall-model", "d")


def _card(tmp_path: Path) -> Path:
    run_dir = tmp_path / "bbbbbbbb-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    _write(
        run_dir, _result(), _skills(73_501), {"type": "system", "subtype": "status", "status": "requesting"}
    )
    return run_dir


def test_t2560_the_watch_files_no_stall_33_s_after_the_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _card(tmp_path)
    sent: list[str] = []
    monkeypatch.setattr(report, "file", lambda signature, *_a, **_k: sent.append(signature))
    StallWatch(tmp_path, clock=lambda: AT + 33, diagnose=_model).tick()
    assert sent == []
    StallWatch(tmp_path, clock=lambda: AT + LIMIT + 5, diagnose=_model).tick()
    assert sent == ["stall-model"]
