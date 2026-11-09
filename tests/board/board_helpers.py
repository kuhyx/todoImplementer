"""Builders shared by the board tests: a fake todo note, run states and a card context."""

from dataclasses import dataclass, replace
from typing import Any

from todoimpl.board.card import Context
from todoimpl.board.state import RunState
from todoimpl.board.types import Credits, Limit

NOW = 1_793_880_000.0
STAGES = (
    "spec",
    "spec_wait",
    "plan",
    "implement",
    "live_check",
    "checks",
    "gate",
    "shipping",
    "shipped",
    "failed",
    "paused_limit",
    "paused_retry",
    "cancelled",
)


@dataclass(frozen=True)
class Note:
    """Stands in for todoimpl.todo_mcp.client.Task."""

    id: str = "c59d2588-0"
    title: str = "Demo task"
    body: str = "Do the demo."
    repo: str | None = "demo"
    status: str = "todo"
    priority: str = "high"
    done_check: str | None = "python demo.py"


def run(**fields: Any) -> RunState:
    """Return a RunState for the demo note (stage `implement`, assignee claude) with fields overridden."""
    base = RunState(task_id="c59d2588-0", stage="implement", assignee="claude", updated=NOW)
    return replace(base, **fields)


def ctx(
    *,
    live: tuple[str, ...] = (),
    limit: Limit | None = None,
    missing: str | None = None,
) -> Context:
    """Return a card context; `missing` makes every repo look absent from disk with that display path."""
    return Context(
        live=frozenset(live),
        limit=limit or Limit(),
        now=NOW,
        repo_missing=lambda repo: missing if repo else None,
    )


LIMITED = Limit(
    active=True, until=NOW + 3600, credits=Credits(enabled=False, state="off", text="fallback off")
)
TAKEOVER = Limit(
    active=True, until=NOW + 3600, credits=Credits(enabled=True, state="ready", text="credits take over")
)
EXHAUSTED = Limit(
    active=True, until=NOW + 3600, credits=Credits(enabled=True, state="exhausted", text="credits exhausted")
)
