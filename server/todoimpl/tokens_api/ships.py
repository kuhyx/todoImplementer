"""Cost per shipped part (board) next to cost per day (manual sessions), for ``/api/tokens/items``.

The board's side is the ship ledger (``repotask/ledger.py``): each line names the sessions of the cycle a part
shipped in. Their store cost is split evenly over the parts that cycle shipped. The manual side is every
session the store holds that no board run started (none inside the run root: worktrees, one-shots, umbrella
managers), grouped by the day it began.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import run_root
from todoimpl.repotask import ledger
from todoimpl.tokens.items import costs
from todoimpl.tokens_api import db

if TYPE_CHECKING:
    import sqlite3

    from todoimpl.tokens_api.db import Filters

_MANUAL = (
    "SELECT key, first_ts, usd, calls FROM session_summary WHERE first_ts BETWEEN ? AND ?"
    " AND (? = '' OR cwd = ? OR cwd LIKE ? || '/%')"
    " AND (cwd IS NULL OR cwd NOT LIKE ? || '/%')"
)


def _stamp(row: dict[str, Any]) -> float | None:
    try:
        return datetime.fromisoformat(str(row["at"])).timestamp()
    except ValueError, KeyError:
        return None


def shipped(conn: sqlite3.Connection, filters: Filters) -> list[dict[str, Any]]:
    """One row per shipped part inside the window: its share of the cycle's session cost."""
    groups: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for row in ledger.read(run_root()):
        stamp = _stamp(row)
        if stamp is not None and filters.since <= stamp <= filters.until:
            groups[str(row.get("card")), int(row.get("cycle") or 1)].append(row)
    sessions = {sid for rows in groups.values() for r in rows for sid in r["sessions"]}
    priced = costs(conn, sorted(sessions))
    out: list[dict[str, Any]] = []
    for rows in groups.values():
        ids = {sid for r in rows for sid in r["sessions"]}
        usd = sum(priced.get(sid, (0.0, 0))[0] for sid in ids)
        calls = sum(priced.get(sid, (0.0, 0))[1] for sid in ids)
        parts = {r.get("part") for r in rows}
        out.extend(
            {
                "part": str(r.get("part")),
                "title": str(r.get("title") or ""),
                "repo": str(r.get("repo") or ""),
                "cycle": int(r.get("cycle") or 1),
                "at": str(r.get("at")),
                "parts": len(parts),
                "sessions": len(ids),
                "calls": calls,
                "cycle_usd": usd,
                "usd": usd / len(parts),
            }
            for r in rows
        )
    return sorted(out, key=lambda r: (r["at"], r["part"]), reverse=True)


def manual(conn: sqlite3.Connection, filters: Filters, board: set[str]) -> list[dict[str, Any]]:
    """One row per day: the sessions no board run started (kuhy's own) and what they cost."""
    cwd = filters.cwd
    days: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    for key, first_ts, usd, calls in conn.execute(
        _MANUAL, (filters.since, filters.until, cwd, cwd, cwd, str(run_root()))
    ):
        if key in board:
            continue
        total = days[db.day_of(first_ts)]
        total[0] += usd or 0.0
        total[1] += calls or 0
        total[2] += 1
    return [
        {"day": day, "sessions": int(t[2]), "calls": int(t[1]), "usd": t[0], "mean_usd": t[0] / t[2]}
        for day, t in sorted(days.items(), reverse=True)
    ]


def payload(conn: sqlite3.Connection, filters: Filters, board: set[str]) -> dict[str, Any]:
    """Return the two tables and the numbers that compare them."""
    parts, days = shipped(conn, filters), manual(conn, filters, board)
    part_usd = sum(r["usd"] for r in parts)
    manual_usd = sum(d["usd"] for d in days)
    sessions = sum(d["sessions"] for d in days)
    return {
        "shipped": parts,
        "manual": days,
        "compare": {
            "shipped_parts": len(parts),
            "shipped_usd": part_usd,
            "usd_per_part": db.ratio(part_usd, len(parts)) or 0.0,
            "manual_sessions": sessions,
            "manual_usd": manual_usd,
            "usd_per_session": db.ratio(manual_usd, sessions) or 0.0,
            "usd_per_day": db.ratio(manual_usd, len(days)) or 0.0,
        },
    }
