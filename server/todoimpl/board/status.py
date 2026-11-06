# ruff: noqa: FBT001
"""THE status of a task, computed only here (rules in DOCS-spec.md, "Single status per task").

The page and the HTTP layer never recompute it: they display `Status`, `Column` and `Needs`.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .state import RunState
    from .types import TaskLike

CLOSED = ("done", "abandoned")


class Status(StrEnum):
    """The one status of a card; values match common.schema.json `status`."""

    BACKLOG = "backlog"
    YOURS = "yours"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    WORKING = "working"
    PAUSED_LIMIT = "paused_limit"
    SHIPPING = "shipping"
    NEEDS_YOU = "needs_you"
    READY_TO_SHIP = "ready_to_ship"
    DONE = "done"


class Column(StrEnum):
    """Board columns, in display order."""

    BACKLOG = "backlog"
    RUNNING = "running"
    NEEDS_YOU = "needs_you"
    READY = "ready"
    DONE = "done"


_COLUMNS = {
    Status.BACKLOG: Column.BACKLOG,
    Status.YOURS: Column.BACKLOG,
    Status.CANCELLED: Column.BACKLOG,
    Status.QUEUED: Column.RUNNING,
    Status.WORKING: Column.RUNNING,
    Status.PAUSED_LIMIT: Column.RUNNING,
    Status.SHIPPING: Column.RUNNING,
    Status.NEEDS_YOU: Column.NEEDS_YOU,
    Status.READY_TO_SHIP: Column.READY,
    Status.DONE: Column.DONE,
}


def column(status: Status) -> Column:
    """Return the board column of a status."""
    return _COLUMNS[status]


def compute(  # noqa: PLR0911 - one return per rule of the spec table
    task: TaskLike,
    run: RunState | None,
    live: bool,
    limit_until: float | None,
) -> Status:
    """Return the single status; the first matching rule wins.

    `live` = a runner thread/process is active for the task; `limit_until` = end of the active plan limit.
    A run with `using_credits` ignores the limit.
    """
    if task.status in CLOSED or (run is not None and run.stage == "shipped"):
        return Status.DONE
    if run is None:
        return Status.YOURS if task.repo is None else Status.BACKLOG
    if run.stage == "cancelled":
        return Status.CANCELLED
    if run.assignee == "human" and not run.error:
        return Status.YOURS
    if run.stage == "gate":
        return Status.READY_TO_SHIP
    if _needs_you(run, live):
        return Status.NEEDS_YOU
    if run.stage == "shipping":
        return Status.SHIPPING
    if run.stage == "paused_limit" or (limit_until is not None and not live and not run.using_credits):
        return Status.PAUSED_LIMIT
    return Status.WORKING if live or run.stage == "paused_retry" else Status.QUEUED


def _needs_you(run: RunState, live: bool) -> bool:
    """Rule 6: the run waits on kuhy."""
    return (
        run.stage in ("failed", "spec_wait")
        or run.error is not None
        or (run.last_tag in ("Q", "A") and not live)
    )


@dataclass(frozen=True)
class Needs:
    """Why a card is in Needs you (needs_kind) and exactly what is needed."""

    kind: str
    text: str

    def to_dict(self) -> dict[str, str]:
        """Return the contract object."""
        return {"kind": self.kind, "text": self.text}


def needs(run: RunState) -> Needs:  # noqa: PLR0911 - one return per kind
    """Return the Needs for a run whose status is NEEDS_YOU."""
    err = run.error
    if run.assignee == "human":
        return Needs("handed_to_you", err or "Claude handed this to you without saying what it needs")
    if run.stage == "spec_wait":
        if run.open_questions():
            return Needs("spec_questions", f"{len(run.open_questions())} open question(s) from Claude")
        if run.last_tag not in ("Q", "A") and not err:
            return Needs("spec_ok", "Every question is answered: click Spec OK to start the plan")
    if run.stage == "failed" and run.checks is not None and not run.checks.get("passed", True):
        return Needs("checks_failed", err or "Checks are still red after the fix attempts")
    if run.stage != "failed" and run.last_tag == "Q":
        return Needs("claude_question", err or "Claude asked a question: answer it with Send to Claude")
    if run.stage != "failed" and run.last_tag == "A":
        return Needs("claude_action", err or "Claude needs you to do something: see the feed")
    return Needs("run_failed", err or "The run stopped without a message")
