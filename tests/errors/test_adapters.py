"""Source adapters: kartka's state.json and the contract file become records."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from errfakes import kartka_entry, rec, write_kartka, write_report
from todoimpl.errors.adapters import SourceError, contract, kartka

if TYPE_CHECKING:
    from pathlib import Path


def test_kartka_entry_maps_to_a_record(tmp_path: Path) -> None:
    path = write_kartka(tmp_path / "s.json", kartka_entry(count=5))
    (found,) = kartka(path, "kartka", "kuhyx/kartka")
    assert (found.app, found.repo, found.signature) == ("kartka", "kuhyx/kartka", "02b0d43d9f")
    assert found.kind == "updates.check"
    assert found.message == "SuwayomiException: x"
    assert found.top_frame == "SuwayomiSource._searchForUnseen (package:kartka/s.dart)"
    assert (found.count, found.first_seen, found.last_seen) == (
        5,
        "2026-11-01T10:00:00Z",
        "2026-11-02T10:00:00Z",
    )
    assert found.build == 0  # kartka's state has no build id: unknown
    assert found.detail == "routes /library; sources suwayomi:1; devices 1"
    assert found.open


def test_kartka_resolved_is_closed_and_a_reported_build_wins(tmp_path: Path) -> None:
    sample = {"error": "boom", "kind": "crash", "build": 77}
    path = write_kartka(
        tmp_path / "s.json",
        kartka_entry("aaa", resolved="2026-11-03T00:00:00Z"),
        kartka_entry("bbb", sample=sample, kinds=[], routes=[], sources=[], devices=[], where=None),
        kartka_entry("ccc", sample={"error": "x", "versionCode": 12}, count=0),
    )
    by_sig = {r.signature: r for r in kartka(path, "kartka", "kuhyx/kartka")}
    assert by_sig["aaa"].open is False
    assert by_sig["bbb"].build == 77
    assert (by_sig["bbb"].kind, by_sig["bbb"].top_frame, by_sig["bbb"].detail) == ("crash", None, None)
    assert by_sig["ccc"].build == 12
    assert by_sig["ccc"].count == 1  # the contract needs at least one


def test_kartka_skips_entries_it_cannot_read(tmp_path: Path) -> None:
    path = write_kartka(tmp_path / "s.json", kartka_entry("ok"))
    text = path.read_text(encoding="utf-8").replace(
        '"signatures": {', '"signatures": {"bad": 5, "worse": {},'
    )
    path.write_text(text, encoding="utf-8")
    assert [r.signature for r in kartka(path, "kartka", "kuhyx/kartka")] == ["ok"]


def test_kartka_message_is_cut_and_a_missing_sample_still_maps(tmp_path: Path) -> None:
    long = write_kartka(tmp_path / "s.json", kartka_entry(sample={"error": "x" * 900}, type="T"))
    (found,) = kartka(long, "kartka", "kuhyx/kartka")
    assert len(found.message) == 300
    bare = write_kartka(tmp_path / "t.json", kartka_entry(sample=None, kinds=None, type="T"))
    (found,) = kartka(bare, "kartka", "kuhyx/kartka")
    assert (found.kind, found.message) == ("error", "T")


@pytest.mark.parametrize("text", ["not json", "[]", '{"signatures": 3}'])
def test_kartka_bad_files_raise_source_error(tmp_path: Path, text: str) -> None:
    path = tmp_path / "s.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SourceError):
        kartka(path, "kartka", "kuhyx/kartka")


def test_a_missing_file_raises_source_error(tmp_path: Path) -> None:
    with pytest.raises(SourceError):
        kartka(tmp_path / "none.json", "kartka", "kuhyx/kartka")
    with pytest.raises(SourceError):
        contract(tmp_path / "none.json")


def test_contract_file_reads_valid_records_and_drops_bad_ones(tmp_path: Path) -> None:
    path = write_report(tmp_path / "x.json", rec(app="tutor", repo="kuhyx/tutor"), {"app": "bad"})
    assert [r.app for r in contract(path)] == ["tutor"]


@pytest.mark.parametrize(
    "text", ["nope", "[]", '{"version": 2, "errors": []}', '{"version": 1, "errors": 4}']
)
def test_contract_bad_documents_raise(tmp_path: Path, text: str) -> None:
    path = tmp_path / "x.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(SourceError):
        contract(path)
