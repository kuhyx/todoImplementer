"""The ledger `<run root>/app-errors.json`: durable, locked, forgiving of a bad file."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from contract_lib import validate
from todoimpl.errors import ledger

if TYPE_CHECKING:
    from pathlib import Path


def test_a_missing_or_broken_ledger_is_empty(tmp_path: Path) -> None:
    assert ledger.load(tmp_path) == {}
    (tmp_path / ledger.FILE).write_text("nope", encoding="utf-8")
    assert ledger.load(tmp_path) == {}
    (tmp_path / ledger.FILE).write_text('{"a:1": 5, "b:2": {"state": "ticket"}}', encoding="utf-8")
    assert ledger.load(tmp_path) == {"b:2": {"state": "ticket"}}
    (tmp_path / ledger.FILE).write_text("[]", encoding="utf-8")
    assert ledger.load(tmp_path) == {}


def test_put_creates_and_merges_an_entry_and_the_file_matches_the_contract(tmp_path: Path) -> None:
    ledger.put(tmp_path, "kartka:1", state="ticket", repo="kuhyx/kartka", title="t", count=2, starts=0)
    ledger.put(tmp_path, "kartka:1", count=5)
    assert ledger.load(tmp_path)["kartka:1"]["count"] == 5
    validate("app-error", ledger.load(tmp_path), "ledger")


def test_drop_forgets_an_entry_and_ignores_a_missing_one(tmp_path: Path) -> None:
    ledger.put(tmp_path, "a:1", state="ticket")
    ledger.drop(tmp_path, "a:1")
    ledger.drop(tmp_path, "a:1")
    assert ledger.load(tmp_path) == {}


def test_mark_shipped_moves_only_ticket_entries(tmp_path: Path) -> None:
    ledger.put(tmp_path, "a:1", state="ticket", starts=1)
    ledger.put(tmp_path, "a:2", state="fixed")
    ledger.mark_shipped(tmp_path, ["a:1", "a:2", "a:3"], "abc123", 99.0)
    data = ledger.load(tmp_path)
    assert (data["a:1"]["state"], data["a:1"]["commit"], data["a:1"]["shipped_at"]) == (
        "shipped",
        "abc123",
        99.0,
    )
    assert data["a:2"]["state"] == "fixed"
    assert "a:3" not in data


def test_parallel_puts_do_not_lose_entries(tmp_path: Path) -> None:
    def work(n: int) -> None:
        ledger.put(tmp_path, f"a:{n}", state="ticket")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(ledger.load(tmp_path)) == 12
