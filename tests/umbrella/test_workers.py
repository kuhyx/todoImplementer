"""The worker attempt log: appended durably, read back, a torn or foreign line skipped."""

from __future__ import annotations

from pathlib import Path

from todoimpl.umbrella import workers


def test_rows_round_trip_in_file_order(tmp_path: Path) -> None:
    workers.record(tmp_path, {"child": "kuhyx/a", "attempt": 1})
    workers.record(tmp_path, {"child": "kuhyx/b", "attempt": 1})
    assert [r["child"] for r in workers.read(tmp_path)] == ["kuhyx/a", "kuhyx/b"]


def test_a_missing_file_reads_as_no_attempts(tmp_path: Path) -> None:
    assert workers.read(tmp_path) == []


def test_a_torn_last_line_after_a_power_cut_and_non_objects_are_skipped(tmp_path: Path) -> None:
    (tmp_path / workers.FILE).write_text('{"child": "kuhyx/a"}\n[1]\n{"child": "kuhy', encoding="utf-8")
    assert workers.read(tmp_path) == [{"child": "kuhyx/a"}]
