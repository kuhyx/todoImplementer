"""``/api/tokens/items``: cost per todoImplementer item, repo and stage.

``todoimpl.tokens.items.session_items`` maps each run session to item, repo and stage;
this joins that to the store's per-session cost over the request's window.
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import run_root
from todoimpl.tokens.items import SessionItem, session_items
from todoimpl.tokens_api import ships

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Callable

    from todoimpl.tokens_api.db import Filters

_SQL = (
    "SELECT key, usd, calls FROM session_summary WHERE first_ts BETWEEN ? AND ?"
    " AND (? = '' OR cwd = ? OR cwd LIKE ? || '/%')"
)


def lookup(conn: sqlite3.Connection) -> dict[str, SessionItem]:
    """Return ``session_id -> SessionItem`` for the runs under the run root."""
    return {row.session_id: row for row in session_items(conn, run_root())}


def _group(rows: dict[tuple[str, ...], list[float]], names: tuple[str, ...]) -> list[dict[str, Any]]:
    """Flat table rows from ``key -> [usd, calls, sessions]``, dearest first."""
    table = [
        {**dict(zip(names, key, strict=True)), "sessions": int(v[2]), "calls": int(v[1]), "usd": v[0]}
        for key, v in rows.items()
    ]
    return sorted(table, key=lambda r: (-r["usd"], *(str(r[n]) for n in names)))


def payload(
    conn: sqlite3.Connection, filters: Filters, find: Callable[[sqlite3.Connection], dict[str, SessionItem]]
) -> dict[str, Any]:
    """Cost by item/repo/stage for the window, plus cost per shipped part and per manual day."""
    known = find(conn)
    cwd = filters.cwd
    by_item: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    by_repo: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    by_stage: dict[tuple[str, ...], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0])
    total = 0.0
    for session_id, usd, calls in conn.execute(_SQL, (filters.since, filters.until, cwd, cwd, cwd)):
        meta = known.get(session_id)
        if meta is None:
            continue
        for rows, key in (
            (by_item, (meta.item_id, meta.repo, meta.stage)),
            (by_repo, (meta.repo,)),
            (by_stage, (meta.stage,)),
        ):
            rows[key][0] += usd or 0.0
            rows[key][1] += calls or 0
            rows[key][2] += 1
        total += usd or 0.0
    return {
        "items": _group(by_item, ("item", "repo", "stage")),
        "repos": _group(by_repo, ("repo",)),
        "stages": _group(by_stage, ("stage",)),
        "total_usd": total,
        **ships.payload(conn, filters, set(known)),
    }
