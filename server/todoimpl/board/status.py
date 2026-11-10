# ruff: noqa: FBT001
"""THE status of a task, computed only here (rules in DOCS-spec.md, "Single status per task").

The page and the HTTP layer never recompute it: they display `Status`, `Column` and `Needs`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from todoimpl.umbrella.note import is_umbrella

from .types import is_manual

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
    Status.CANCELLED: Column.DONE,
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

    `live` = a runner thread/process is active for the task; `limit_until` = end of the plan limit when it
    holds turns back (None while the free credits take over).
    """
    if task.status == "done" or (run is not None and run.stage == "shipped"):
        return Status.DONE
    if task.status == "abandoned" or (run is not None and run.stage == "cancelled"):
        return Status.CANCELLED
    if is_manual(task.title) or (run is None and task.repo is None and not is_umbrella(task.body)):
        return Status.YOURS
    if run is None:
        return Status.BACKLOG
    if run.assignee == "human" and not run.error:
        return Status.YOURS
    if run.stage == "gate":
        return Status.READY_TO_SHIP
    if _needs_you(run, live):
        return Status.NEEDS_YOU
    if run.stage == "shipping":
        return Status.SHIPPING
    if run.stage == "paused_limit" or (limit_until is not None and not live):
        return Status.PAUSED_LIMIT
    return Status.WORKING if live or run.stage == "paused_retry" else Status.QUEUED


def _needs_you(run: RunState, live: bool) -> bool:
    """Rule 6: the run waits on kuhy; paused_retry waits on its own timer, whatever tag it carries."""
    if run.stage == "paused_retry":
        return False
    return (
        run.stage in ("failed", "spec_wait")
        or run.error is not None
        or (run.last_tag in ("Q", "A") and not live)
    )
