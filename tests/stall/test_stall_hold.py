"""A sub-agent thinking for minutes is work; its request is judged by the tokens it got back (T2563).

2026-11-27, card ba5c3ff1-0: the main thread had ended its turn; a background sub-agent got a tool result at
11:06:46.046, sent its next request 10 ms later and wrote nothing until a thinking block at 11:08:59.433:
11,817 output tokens in 133 s (89 tokens/s; the slowest of 111 sub-agent requests over 30 s that day was
82). claude writes no partial line of a sub-agent anywhere, so the watch filed `stall-model` at 66 s. Now a
quiet card whose sub-agent has a request out is held up to `HOLD`; when the answer comes, the quiet left
after the time its tokens took at `FLOOR` tokens/s is filed if it is over a minute, and a request with no
answer by `HOLD` is filed like any quiet. The fixture is that transcript's slice, every text blanked.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import pytest
from todoimpl.runner import orphans
from todoimpl.stall import hold, report, scan, subagent
from todoimpl.stall.watch import StallWatch

FIXTURE = Path(__file__).parent.parent / "fixtures" / "stall" / "subagent-ba5c3ff1.jsonl"
STEM = "implement-1795777091.267"
SID = "809438ea-902b-4567-89a4-256fab05fefc"
CWD = "/w/ba5c3ff1-0/wt"
RESULT = "2026-11-27T11:06:46.046Z"
SINCE = datetime.fromisoformat(RESULT).timestamp()
ASKED = datetime.fromisoformat("2026-11-27T11:06:46.056Z").timestamp()
ANSWERED = datetime.fromisoformat("2026-11-27T11:08:59.433Z").timestamp()
TICK = 1795777671.9533844  # the real filing tick, quiet 66 s


def _card(tmp_path: Path) -> Path:
    run_dir = tmp_path / "ba5c3ff1-0"
    run_dir.mkdir()
    orphans.write(run_dir, stem=STEM, pid=os.getpid(), start=orphans.start_of(os.getpid()))
    content = [{"type": "tool_result", "tool_use_id": "toolu_b", "content": ""}]
    rows = [
        {"type": "system", "subtype": "init", "cwd": CWD, "session_id": SID},
        {
            "type": "user",
            "timestamp": RESULT,
            "parent_tool_use_id": "toolu_a",
            "message": {"content": content},
        },
    ]
    stream = run_dir / f"{STEM}.stream.jsonl"
    stream.write_text("".join(json.dumps(r) + "\n" for r in rows), "utf-8")
    os.utime(stream, (SINCE, SINCE))
    return run_dir


def _transcript(*, answer: int | None) -> Path:
    """Write the sub-agent's transcript; `answer` is the answer's output tokens, None while it waits."""
    rows = FIXTURE.read_text("utf-8").splitlines()
    last = json.loads(rows.pop())
    if answer is not None:
        last["message"]["usage"]["output_tokens"] = answer
        rows.append(json.dumps(last))
    path = subagent.PROJECTS / "-w-ba5c3ff1-0-wt" / SID / "subagents" / "agent-aec65edd3f9af09d7.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(r + "\n" for r in rows), "utf-8")
    at = ASKED if answer is None else ANSWERED
    os.utime(path, (at, at))
    return path


def _tick(tmp_path: Path, now: float) -> list[str]:
    """One tick of a fresh watch, as after a restart: what it filed."""
    filed: list[str] = []

    def _diagnose(_run: scan.Running) -> tuple[str, str]:
        filed.append("stall-model")
        return ("stall-model", "no command runs: waiting on the model")

    StallWatch(tmp_path, clock=lambda: now, diagnose=_diagnose).tick()
    return filed


@pytest.fixture
def sent(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    calls: list[str] = []
    monkeypatch.setattr(
        report, "file", lambda signature, detail, *_a, **_k: calls.append(f"{signature}|{detail}")
    )
    return calls


def test_t2563_the_replayed_request_is_held_then_cleared_by_its_tokens(
    tmp_path: Path, sent: list[str]
) -> None:
    _card(tmp_path)
    _transcript(answer=None)
    assert _tick(tmp_path, TICK) == []
    assert _tick(tmp_path, ANSWERED - 1) == []
    _transcript(answer=11_817)
    assert _tick(tmp_path, ANSWERED + 1) == []
    assert sent == []
    assert not (tmp_path / report.LOG).exists()
    assert hold.load(tmp_path) == {}


def test_t2563_an_answer_too_small_for_its_wait_files_the_quiet(tmp_path: Path, sent: list[str]) -> None:
    _card(tmp_path)
    _transcript(answer=None)
    assert _tick(tmp_path, TICK) == []
    _transcript(answer=50)
    _tick(tmp_path, ANSWERED + 1)
    assert [s.split("|")[0] for s in sent] == ["stall-model"]
    rows = [json.loads(r) for r in (tmp_path / report.LOG).read_text("utf-8").splitlines()]
    assert [(r["since"], r.get("idle"), "ended" in r) for r in rows] == [
        (SINCE, 133, False),
        (SINCE, None, True),
    ]
    assert hold.load(tmp_path) == {}


def test_t2563_a_request_with_no_answer_by_the_hold_is_filed(tmp_path: Path, sent: list[str]) -> None:
    _card(tmp_path)
    _transcript(answer=None)
    assert _tick(tmp_path, TICK) == []
    assert _tick(tmp_path, ASKED + hold.HOLD + 5) == ["stall-model"]
    assert len(sent) == 1


def test_t2563_a_long_wait_before_a_normal_answer_is_filed(tmp_path: Path, sent: list[str]) -> None:
    """78 s with no token, then 5,000 tokens at 90 tokens/s: the wait is a stall, the writing is not."""
    _card(tmp_path)
    _transcript(answer=None)
    assert _tick(tmp_path, TICK) == []
    _transcript(answer=5_000)
    _tick(tmp_path, ANSWERED + 1)
    assert [s.split("|")[0] for s in sent] == ["stall-model"]
    rows = [json.loads(r) for r in (tmp_path / report.LOG).read_text("utf-8").splitlines()]
    assert rows[0]["idle"] == 71
