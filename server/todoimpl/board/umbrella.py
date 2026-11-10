"""The board's view of an umbrella note: child counts for the card, child rows and rounds for the drawer.

The service overlays `run.extra["umbrella_view"] = {"rows": [...]}` (read from the child run dirs); the round
record lives in `run.extra["umbrella"]` (written by the runner). Without a run the rows come from the note.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl.umbrella.note import children, is_umbrella

if TYPE_CHECKING:
    from .state import RunState
    from .types import TaskLike

ROUND_KEYS = ("n", "width", "next", "children")
VIEW = "umbrella_view"
RECORD = "umbrella"
_BUCKETS = {
    "done": "done",
    "working": "running",
    "queued": "running",
    "shipping": "running",
    "paused_limit": "running",
    "ready_to_ship": "ready",
    "backlog": "queued",
}


def bucket(status: str) -> str:
    """Return the card counter a child's status feeds: done, running, ready, queued or failed."""
    return _BUCKETS.get(status, "failed")


def _record(run: RunState | None) -> dict[str, Any]:
    found = run.extra.get(RECORD) if run is not None else None
    return found if isinstance(found, dict) else {}


def _rows(task: TaskLike, run: RunState | None) -> list[dict[str, Any]]:
    view = run.extra.get(VIEW) if run is not None else None
    if isinstance(view, dict) and isinstance(view.get("rows"), list):
        return list(view["rows"])
    return [
        {
            "id": c.cid,
            "repo": c.repo,
            "title": c.title,
            "status": "done" if c.done else "backlog",
            "stage": None,
            "round": None,
            "verdict": None,
            "free": None,
            "error": None,
            "cost_usd": 0,
            "issues": 0,
        }
        for c in children(task.body, task.id.partition("-")[0])
        if not c.dropped
    ]


def card_view(task: TaskLike, run: RunState | None) -> dict[str, Any] | None:
    """Return the card's `umbrella` object (child counts, round width), None for a plain note."""
    if not is_umbrella(task.body):
        return None
    return counts(_rows(task, run), _record(run))


def counts(rows: list[dict[str, Any]], record: dict[str, Any]) -> dict[str, Any]:
    """Return the `umbrella_counts` object: children per bucket, the next width, rounds done, issues."""
    found = dict.fromkeys(("done", "running", "ready", "queued", "failed"), 0)
    for row in rows:
        found[bucket(str(row["status"]))] += 1
    return {
        **found,
        "total": len(rows),
        "width": int(record.get("width", 1)),
        "round": len(record.get("rounds", [])),
        "issues": sum(int(row.get("issues", 0)) for row in rows),
    }


def detail(task: TaskLike, run: RunState | None) -> dict[str, Any] | None:
    """Return the drawer's `umbrella` object (child rows, round history), None for a plain note."""
    if not is_umbrella(task.body):
        return None
    record = _record(run)
    rounds = [
        {k: r[k] for k in ROUND_KEYS} for r in record.get("rounds", [])
    ]  # timestamps are for the tracking view
    return {
        "width": int(record.get("width", 1)),
        "round": len(rounds),
        "rows": _rows(task, run),
        "rounds": rounds,
    }
