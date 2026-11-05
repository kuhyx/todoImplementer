from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl.tokens import items, schema

if TYPE_CHECKING:
    from pathlib import Path


def _stream(path: Path, *events: dict[str, Any] | str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [e if isinstance(e, str) else json.dumps(e) for e in events]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _result(sid: object) -> dict[str, Any]:
    return {"type": "result", "session_id": sid}


def _store(tmp_path: Path, rows: dict[str, tuple[float, int]]) -> Any:
    conn = schema.connect(tmp_path / "tokens.sqlite")
    for key, (usd, calls) in rows.items():
        conn.execute("INSERT INTO session_summary (key, usd, calls) VALUES (?,?,?)", (key, usd, calls))
    conn.commit()
    return conn


def _runs(root: Path) -> None:
    (root / "aaaa1111-1").mkdir(parents=True)
    (root / "aaaa1111-1" / "state.json").write_text('{"repo": "todo"}', encoding="utf-8")
    _stream(root / "aaaa1111-1" / "plan-1730000000.000.stream.jsonl", {"type": "system"}, _result("s-plan"))
    _stream(
        root / "aaaa1111-1" / "implement-1730000100.500.stream.jsonl",
        "not json",
        "[1]",
        _result("s-impl"),
        _result("s-impl"),
        _result(7),
        _result(""),
        {"type": "assistant", "session_id": "ignored"},
    )
    (root / "bbbb2222-1").mkdir()
    _stream(root / "bbbb2222-1" / "review-x-1730000200.000.stream.jsonl", _result("s-plan"), _result("s-rev"))
    (root / "stray.txt").write_text("not a run dir", encoding="utf-8")


def test_stage_is_the_role_in_the_stream_name(tmp_path: Path) -> None:
    assert items.stage_of(tmp_path / "plan-1730000000.000.stream.jsonl") == "plan"
    assert items.stage_of(tmp_path / "review-x-1.000.stream.jsonl") == "review-x"


def test_session_items_join_item_repo_stage_and_cost(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    _runs(root)
    conn = _store(tmp_path, {"s-plan": (1.5, 10), "s-impl": (4.0, 40)})
    found = {row.session_id: row for row in items.session_items(conn, root)}
    conn.close()
    assert set(found) == {"s-plan", "s-impl", "s-rev"}
    want = items.SessionItem("s-plan", "aaaa1111-1", "todo", "plan", 1.5, 10, ingested=True)
    assert found["s-plan"] == want
    assert found["s-impl"].stage == "implement"
    assert found["s-rev"] == items.SessionItem("s-rev", "bbbb2222-1", "", "review-x")
    assert not found["s-rev"].ingested


def test_item_costs_sum_per_item_and_stage_most_expensive_first(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    _runs(root)
    _stream(root / "aaaa1111-1" / "implement-1730000300.000.stream.jsonl", _result("s-impl2"))
    conn = _store(tmp_path, {"s-plan": (1.5, 10), "s-impl": (4.0, 40), "s-impl2": (1.0, 5)})
    rows = items.item_costs(conn, root)
    conn.close()
    assert [(r.item_id, r.stage, r.usd, r.calls, r.sessions) for r in rows] == [
        ("aaaa1111-1", "implement", 5.0, 45, 2),
        ("aaaa1111-1", "plan", 1.5, 10, 1),
        ("bbbb2222-1", "review-x", 0.0, 0, 1),
    ]


def test_state_json_that_is_not_an_object_or_unreadable_gives_no_repo(tmp_path: Path) -> None:
    root = tmp_path / "runs"
    (root / "c-1").mkdir(parents=True)
    (root / "c-1" / "state.json").write_text("[1, 2]", encoding="utf-8")
    _stream(root / "c-1" / "plan-1.000.stream.jsonl", _result("s1"))
    (root / "d-1").mkdir()
    (root / "d-1" / "state.json").write_text('{"repo": 3}', encoding="utf-8")
    _stream(root / "d-1" / "plan-1.000.stream.jsonl", _result("s2"))
    (root / "e-1" / "state.json").mkdir(parents=True)
    _stream(root / "e-1" / "plan-1.000.stream.jsonl", _result("s3"))
    conn = _store(tmp_path, {})
    repos = {r.session_id: r.repo for r in items.session_items(conn, root)}
    conn.close()
    assert repos == {"s1": "", "s2": "", "s3": ""}


def test_empty_run_root_has_no_sessions(tmp_path: Path) -> None:
    conn = _store(tmp_path, {})
    assert items.session_items(conn, tmp_path / "missing") == []
    conn.close()
