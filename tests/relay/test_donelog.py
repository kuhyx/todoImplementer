"""The done-log file: what survives a reload, what is dropped, and what never reaches the disk."""

import json
from pathlib import Path

from todoimpl.relay.donelog import KEEP_MS, DoneLog

NOW = 1_800_000_000_000


def test_reload_keeps_young_rows_and_drops_old_and_broken_ones(tmp_path: Path) -> None:
    path = tmp_path / "done.jsonl"
    rows = [
        json.dumps({"rid": "young", "at": NOW - 1000, "result": {"ok": True}}),
        json.dumps({"rid": "old", "at": NOW - KEEP_MS - 1, "result": {"ok": True}}),
        "not json",
        json.dumps({"rid": "no result", "at": NOW}),
    ]
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")
    log = DoneLog(path, now_ms=NOW)
    assert log.get("young") == {"ok": True}
    assert log.get("old") is None
    assert path.read_text(encoding="utf-8") == rows[0] + "\n"


def test_read_kinds_and_a_pathless_log_stay_in_memory(tmp_path: Path) -> None:
    path = tmp_path / "relay" / "done.jsonl"
    log = DoneLog(path)
    log.add("read", {"ok": True}, durable=False)
    assert log.get("read") == {"ok": True}
    assert not path.exists()
    memory = DoneLog(None)
    memory.add("write", {"ok": True}, durable=True)
    assert memory.get("write") == {"ok": True}
    log.add("write", {"ok": True}, durable=True)
    assert DoneLog(path).get("write") == {"ok": True}
