"""Edges of the held quiet (T2563): reading requests and answers, torn state, work that comes back."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from todoimpl.stall import hold, request

if TYPE_CHECKING:
    from pathlib import Path

T0 = 1795777606.0


def _iso(offset: float) -> str:
    return datetime.fromtimestamp(T0 + offset, UTC).isoformat()


def _write(path: Path, *rows: object) -> Path:
    path.write_text("".join((r if isinstance(r, str) else json.dumps(r)) + "\n" for r in rows), "utf-8")
    return path


def _req(offset: float) -> dict[str, object]:
    return {"type": "api-request", "timestamp": _iso(offset)}


def _said(offset: float, tokens: int) -> dict[str, object]:
    return {"type": "assistant", "timestamp": _iso(offset), "message": {"usage": {"output_tokens": tokens}}}


def test_t2563_no_request_line_and_no_message_is_no_request(tmp_path: Path) -> None:
    other = {"type": "attachment", "timestamp": _iso(0)}
    path = _write(tmp_path / "a.jsonl", other, {"type": "user"}, "{torn", [1])
    assert request.asked(path) is None


def test_t2563_a_request_behind_a_stamped_side_line_is_out(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.jsonl", _req(0), {"type": "attachment", "timestamp": _iso(1)})
    assert request.asked(path) == T0


def test_t2563_the_answer_is_the_first_message_after_its_own_request(tmp_path: Path) -> None:
    rows = [
        _req(0),
        {"type": "attachment", "timestamp": _iso(1)},
        _said(130, 9000),
        _said(131, 9000),
        {"type": "user", "timestamp": _iso(132)},
        _req(133),
    ]
    path = _write(tmp_path / "a.jsonl", *rows, _said(140, 7), {"type": "assistant"})
    assert request.answer(path, T0) == (T0 + 130, 9000)
    assert request.answer(path, T0 + 133) == (T0 + 140, 7)
    assert request.answer(path, T0 + 1) is None  # no such request in the transcript
    tokenless = _write(
        tmp_path / "b.jsonl", _req(0), {"type": "assistant", "timestamp": _iso(5), "message": {}}
    )
    assert request.answer(tokenless, T0) == (T0 + 5, 0)


def test_t2563_torn_hold_state_is_dropped(tmp_path: Path) -> None:
    (tmp_path / hold.FILE).write_text(json.dumps({"x": {"bogus": 1}, "y": "z"}), "utf-8")
    assert hold.load(tmp_path) == {}
    (tmp_path / hold.FILE).write_text("[]", "utf-8")
    assert hold.load(tmp_path) == {}


def test_t2563_a_card_without_a_turn_record_asks_nothing(tmp_path: Path) -> None:
    assert hold.asking(tmp_path, T0) is None


def test_t2563_work_coming_back_cuts_the_judged_quiet(tmp_path: Path) -> None:
    path = _write(tmp_path / "a.jsonl", _req(0))
    h = hold.Held("c-0", T0 - 1, str(path), T0)
    first = hold.review(tmp_path, {"k": h}, {"c-0": T0 + 70}, T0 + 80, 60.0)
    assert first == {"k": hold.Held("c-0", T0 - 1, str(path), T0, back=T0 + 70)}
    assert hold.review(tmp_path, first, {"c-0": T0 + 90}, T0 + 95, 60.0) == first  # the first return stays
    assert hold.review(tmp_path, first, {}, T0 + 95, 60.0) == {}  # the turn is over
    _write(path, _req(0), _said(200, 50))
    assert hold.quiet(first["k"]) == 71.0  # cut at T0+70, not at the answer
    assert hold.review(tmp_path, first, {"c-0": T0 + 200}, T0 + 205, 80.0) == {}  # 71 s: not over the limit
    assert not (tmp_path / "stalls.jsonl").exists()
