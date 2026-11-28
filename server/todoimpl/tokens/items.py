"""Join todoImplementer runs (`<run_root>/<item id>/*.stream.jsonl` result events) to the token store."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Iterator
    from pathlib import Path

STREAM_SUFFIX = ".stream.jsonl"
STATE_FILE = "state.json"


@dataclass(frozen=True)
class SessionItem:
    """One claude session of one run, with its cost once the store has it."""

    session_id: str
    item_id: str
    repo: str
    stage: str
    usd: float = 0.0
    calls: int = 0
    ingested: bool = False


@dataclass(frozen=True)
class ItemCost:
    """Cost of one item in one stage, summed over its sessions."""

    item_id: str
    repo: str
    stage: str
    usd: float
    calls: int
    sessions: int


def _json_object(text: str) -> dict[str, Any] | None:
    try:
        loaded = json.loads(text)
    except ValueError:
        return None
    return loaded if isinstance(loaded, dict) else None


def _repo_of(run_dir: Path) -> str:
    try:
        state = _json_object((run_dir / STATE_FILE).read_text(encoding="utf-8"))
    except OSError:
        return ""
    repo = state.get("repo") if state else None
    return repo if isinstance(repo, str) else ""


def stream_sessions(stream: Path) -> list[str]:
    """Return the session ids of a stream's result events, first seen first."""
    found: dict[str, None] = {}
    with stream.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            event = _json_object(line)
            sid = event.get("session_id") if event else None
            if event and event.get("type") == "result" and isinstance(sid, str) and sid:
                found[sid] = None
    return list(found)


def stage_of(stream: Path) -> str:
    """Return the role part of ``<role>-<epoch>.stream.jsonl``."""
    return stream.name.removesuffix(STREAM_SUFFIX).rsplit("-", 1)[0]


def _run_sessions(run_root: Path) -> Iterator[tuple[str, str, str, str]]:
    for run_dir in sorted(p for p in run_root.glob("*") if p.is_dir()):
        repo = _repo_of(run_dir)
        for stream in sorted(run_dir.glob(f"*{STREAM_SUFFIX}")):
            for sid in stream_sessions(stream):
                yield sid, run_dir.name, repo, stage_of(stream)


def costs(conn: sqlite3.Connection, ids: list[str]) -> dict[str, tuple[float, int]]:
    """Return `session id -> (usd, calls)` for the ids the store holds."""
    rows = conn.execute(
        "SELECT key, usd, calls FROM session_summary WHERE key IN (SELECT value FROM json_each(?))",
        (json.dumps(ids),),
    )
    return {key: (usd, calls) for key, usd, calls in rows}


def session_items(db: sqlite3.Connection, run_root: Path) -> list[SessionItem]:
    """Map each session under ``run_root`` to item, repo, stage and store cost (first stream wins)."""
    seen: dict[str, tuple[str, str, str]] = {}
    for sid, item, repo, stage in _run_sessions(run_root):
        seen.setdefault(sid, (item, repo, stage))
    priced = costs(db, list(seen))
    return [
        SessionItem(sid, item, repo, stage, *priced.get(sid, (0.0, 0)), ingested=sid in priced)
        for sid, (item, repo, stage) in seen.items()
    ]


def item_costs(db: sqlite3.Connection, run_root: Path) -> list[ItemCost]:
    """Sum :func:`session_items` per item and stage, most expensive first."""
    sums: dict[tuple[str, str, str], list[float]] = defaultdict(lambda: [0.0, 0, 0])
    for row in session_items(db, run_root):
        total = sums[row.item_id, row.repo, row.stage]
        total[0] += row.usd
        total[1] += row.calls
        total[2] += 1
    rows = [
        ItemCost(item, repo, stage, t[0], int(t[1]), int(t[2])) for (item, repo, stage), t in sums.items()
    ]
    return sorted(rows, key=lambda r: (-r.usd, r.item_id, r.stage))
