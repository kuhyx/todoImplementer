"""Child rows of an umbrella, read from the child run dirs: one server-computed status per child.

Used by the board overlay (what the drawer and the card counts show) and by the runner's settle step.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.board.status import compute
from todoimpl.board.umbrella import VIEW
from todoimpl.runner.pipeline import WORK_STAGES

from . import issues
from .store import RECORD, child_dir

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.card import Context
    from todoimpl.board.state import RunState


@dataclass(frozen=True)
class KidTask:
    """A child as the board's `compute` sees a note."""

    id: str
    title: str
    repo: str
    status: str
    body: str = ""
    priority: str = "medium"
    done_check: str | None = None
    created_by: str = "claude"


def child_state(run_dir: Path, cid: str) -> RunState | None:
    """Load a child's state; an unreadable one reads as a failed run that says why."""
    try:
        return store.load(child_dir(run_dir, cid))
    except StateError as exc:
        return store.RunState(task_id=cid, stage="failed", error=str(exc))


def _row(
    kid: dict[str, Any],
    child: RunState | None,
    counts: dict[str, int],
    *,
    live: bool,
    limit_until: float | None,
) -> dict[str, Any]:
    task = KidTask(kid["id"], kid["title"], kid["repo"], "done" if kid["done"] else "todo")
    working = live and child is not None and child.stage in (*WORK_STAGES, "shipping")
    verdict = child.extra.get("verdict") if child is not None else None
    return {
        "id": kid["id"],
        "repo": kid["repo"],
        "title": kid["title"],
        "status": compute(task, child, working, limit_until).value,
        "stage": child.stage if child is not None else None,
        "round": child.extra.get("umbrella_round") if child is not None else None,
        "verdict": verdict.get("kind") if isinstance(verdict, dict) else None,
        "free": child.extra.get("free") if child is not None else None,
        "error": child.error if child is not None else None,
        "cost_usd": child.cost_usd if child is not None else 0,
        "issues": counts.get(kid["repo"], 0),
    }


def rows(
    run_dir: Path, st: RunState, *, live: bool, limit_until: float | None
) -> tuple[list[dict[str, Any]], float]:
    """Return (a row per child in the umbrella's order, the children's summed cost)."""
    counts = issues.counts(run_dir)
    out, cost = [], 0.0
    for kid in st.extra.get(RECORD, {}).get("kids", []):
        child = child_state(run_dir, kid["id"])
        out.append(_row(kid, child, counts, live=live, limit_until=limit_until))
        cost += child.cost_usd if child is not None else 0.0
    return out, cost


def overlay(run_dir: Path, st: RunState, *, live: bool, limit_until: float | None) -> RunState:
    """Return the umbrella run with its child rows attached and the children's cost added (not saved)."""
    if RECORD not in st.extra:
        return st
    found, cost = rows(run_dir, st, live=live, limit_until=limit_until)
    return replace(st, extra={**st.extra, VIEW: {"rows": found}}, cost_usd=round(st.cost_usd + cost, 6))


def overlay_for(context: Callable[[], Context], run_dir: Path, st: RunState) -> RunState:
    """`overlay` for a run that may be an umbrella: the live set and the limit come from the board context."""
    if RECORD not in st.extra:
        return st
    ctx = context()
    until = ctx.limit.until if ctx.limit.holds else None
    return overlay(run_dir, st, live=st.task_id in ctx.live, limit_until=until)
