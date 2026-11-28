"""Per-call token inspector for one session's main transcript.

One row per assistant message (the store keeps one ``turns`` row per message
id, streamed chunks already folded). Context is input + cache write + cache
read; ``fixed`` is the first call's context (the standing prompt), the rest
accumulated. ``output`` is the usage ``output_tokens``, which already includes
thinking. Cost is ``turns.usd``: the call's usage priced at ingest with
``tokens/prices.json`` (:func:`todoimpl.tokens.prices.price_of`), so the rows sum to
the session's own spend.
Subagents are separate sessions: their spend shows under the ``subagent`` class
only as the main call that read their result.
"""

from __future__ import annotations

from bisect import bisect_right
from collections import defaultdict
from typing import TYPE_CHECKING, Any

from todoimpl.tokens_api import call_triggers as triggers

if TYPE_CHECKING:
    import sqlite3

_TURNS = (
    "SELECT ts, prompt_idx, model, input, cache_write, cache_read, output, usd"
    " FROM turns WHERE key = ? ORDER BY ts"
)
_CALLS = "SELECT ts, name, family, target, images, result_tokens FROM calls WHERE key = ? ORDER BY ts"


def _issued(conn: sqlite3.Connection, key: str, starts: list[float]) -> list[list[triggers.Call]]:
    """Tool calls per turn: a call belongs to the last turn that began before it."""
    issued: list[list[triggers.Call]] = [[] for _ in starts]
    for ts, *call in conn.execute(_CALLS, (key,)):
        at = bisect_right(starts, ts) - 1
        if at >= 0:
            issued[at].append(triggers.Call(*call))
    return issued


def _classes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per-class totals, dearest first."""
    total = sum(r["usd"] for r in rows)
    by: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"calls": 0, "usd": 0.0, "output": 0, "context": 0, "accumulated": 0}
    )
    for row in rows:
        acc = by[row["trigger"]]
        acc["calls"] += 1
        acc["usd"] += row["usd"]
        acc["output"] += row["output"]
        acc["context"] += row["context"]
        acc["accumulated"] += row["accumulated"]
    return sorted(
        (
            {"trigger": name, **acc, "share": acc["usd"] / total if total else None}
            for name, acc in by.items()
        ),
        key=lambda c: -c["usd"],
    )


def stream(conn: sqlite3.Connection, key: str) -> dict[str, Any]:
    """Return the call rows, their per-class totals and the fixed context."""
    turns = conn.execute(_TURNS, (key,)).fetchall()
    issued = _issued(conn, key, [t[0] for t in turns])
    rows: list[dict[str, Any]] = []
    fixed = 0
    for at, turn in enumerate(turns):
        context = (turn[3] or 0) + (turn[4] or 0) + (turn[5] or 0)
        fixed = context if at == 0 else fixed
        first = at == 0 or turn[1] != turns[at - 1][1]
        rows.append(
            {
                "idx": at + 1,
                "ts": turn[0],
                "prompt_idx": turn[1],
                "model": turn[2],
                "trigger": triggers.PROMPT if first else triggers.trigger(issued[at - 1]),
                "context": context,
                "fixed": min(fixed, context),
                "accumulated": max(context - fixed, 0),
                "output": turn[6] or 0,
                "usd": turn[7] or 0.0,
            }
        )
    return {"fixed": fixed, "stream": rows, "classes": _classes(rows)}
