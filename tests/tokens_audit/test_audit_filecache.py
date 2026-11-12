"""The per-file audit cache: location, staleness, best-effort failure, pruning (T1997)."""

from __future__ import annotations

import os
from pathlib import Path

import audit_notes_fixtures as fx
import pytest
from todoimpl.tokens import prices
from todoimpl.tokens.audit import filecache, notes_backlog, notes_cost, unused


def test_cache_dir_prefers_todoimpl_home_then_xdg_then_home(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert filecache.cache_dir() == Path.home() / ".cache" / "todoimpl" / "audit"
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg"))
    assert filecache.cache_dir() == tmp_path / "xdg" / "todoimpl" / "audit"
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "t"))
    assert filecache.cache_dir() == tmp_path / "t" / "cache" / "audit"


def test_load_returns_stored_payload_until_the_file_changes(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("one", encoding="utf-8")
    assert filecache.load("k", path) is None
    filecache.store("k", path, {"x": [1, 2]})
    assert filecache.load("k", path) == {"x": [1, 2]}
    assert filecache.load("k", path, "other") is None
    path.write_text("three", encoding="utf-8")
    assert filecache.load("k", path) is None


def test_corrupt_entry_is_a_miss(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("one", encoding="utf-8")
    filecache.store("k", path, 1)
    entry = next(filecache.cache_dir().glob("k/*.json"))
    for bad in ("{not json", "[]", '{"path": 1}'):
        entry.write_text(bad, encoding="utf-8")
        assert filecache.load("k", path) is None


def test_store_failure_is_ignored(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("one", encoding="utf-8")
    blocker = tmp_path / "blocked"
    blocker.write_text("a file where the cache dir should be", encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_HOME", str(blocker))
    filecache.store("k", path, 1)
    assert filecache.load("k", path) is None
    filecache.store("k", tmp_path / "missing.jsonl", 1)


def test_prune_drops_only_idle_entries(tmp_path: Path) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("one", encoding="utf-8")
    filecache.store("session", path, 1)
    filecache.store("facts", path, 2)
    now = max(e.stat().st_mtime for e in filecache.cache_dir().glob("*/*.json"))
    assert filecache.prune(now + 20 * filecache.DAY_SECONDS) == 1  # session: 14 days
    assert filecache.load("facts", path) == 2
    assert filecache.prune(now + 100 * filecache.DAY_SECONDS) == 1  # facts: 90 days
    assert filecache.prune() == 0


def test_prune_survives_vanishing_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "a.jsonl"
    path.write_text("one", encoding="utf-8")
    filecache.store("session", path, 1)

    def gone(self: Path, *, missing_ok: bool = False) -> None:
        raise FileNotFoundError(self)

    monkeypatch.setattr(Path, "unlink", gone)
    assert filecache.prune(1e12) == 0


def test_file_spend_is_cached_per_price_book(tmp_path: Path) -> None:
    root = tmp_path / "projects"
    path = fx.transcript(root, "s1", [fx.tool_use("Bash", {"command": "ls"}, usd_tokens=1_000_000)])
    book = prices.load()
    first = notes_cost.file_spend(path, book)
    assert first.usd > 0
    assert notes_cost.file_spend(path, book) == first
    cheap = prices.PriceBook(
        {k: prices.Price(0.0, 0.0, 0.0) for k in book.models},
        book.default,
    )
    assert notes_cost.file_spend(path, cheap).usd == 0.0
    assert notes_cost.file_spend(path, book) == first


def test_dump_statuses_are_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    dump = fx.dump(tmp_path / "dumps", "2026-10-20", {fx.NOTE_A: (2, "2026-10-20T10:00:00.000Z")})
    cold = notes_backlog.first_seen(dump.parent)
    assert cold[fx.NOTE_A]["done"] > 0
    monkeypatch.setattr(notes_backlog, "_read_dump", lambda _: pytest.fail("re-read"))
    assert notes_backlog.first_seen(dump.parent) == cold


def test_unused_counts_are_cached_per_file(transcripts_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    now = 1_000_000_000.0
    path = transcripts_dir / "recent.jsonl"
    path.write_text('{"name":"mcp__aseprite__draw_line"}\n{"name":"mcp__aseprite__x"}\n', encoding="utf-8")
    os.utime(path, (now - 86400, now - 86400))
    cold = unused.usage_for(["aseprite"], unused._MCP_CALL, now=now)
    assert cold[0].short_calls == 2
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("re-read"))
    assert unused.usage_for(["aseprite"], unused._MCP_CALL, now=now) == cold


@pytest.fixture
def transcripts_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "projects"
    (root / "proj").mkdir(parents=True)
    monkeypatch.setattr(unused, "TRANSCRIPT_ROOT", root)
    return root / "proj"
