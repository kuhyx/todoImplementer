# ruff: noqa: FBT001
"""THE status of a task, computed only here (rules in DOCS-spec.md, "Single status per task").

The page and the HTTP layer never recompute it: they display `Status`, `Column` and `Needs`.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

from todoimpl.errors.marks import PHONE

from .norepo import is_yours
from .parts import kuhys

if TYPE_CHECKING:
    from .state import RunState
    from .types import TaskLike

SHIP_STEP = "ship_step"  # run.extra: the step a shipping run is in (T2060)
WAITS_FOR = "waits_for"  # run.extra: what an idle turn waits on, the build lock or a background job (T2124)
CLOSED = ("done", "abandoned")
DONE_STAGES = ("shipped", "closed")
MANUAL_STAGE = "done_manually"  # kuhy did the work himself (T2064); the run ended with no push
CYCLE_ENDS = ("shipped", MANUAL_STAGE)  # a repo task's run is over here; parts left make it Backlog again


class Status(StrEnum):
    """The one status of a card; values match common.schema.json `status`."""

    BACKLOG = "backlog"
    YOURS = "yours"
    CANCELLED = "cancelled"
    QUEUED = "queued"
    WORKING = "working"
    PAUSED_LIMIT = "paused_limit"
    SHIPPING = "shipping"
    WAITING_PHONE_UPDATE = "waiting_phone_update"
    NEEDS_YOU = "needs_you"
    DONE = "done"
    DONE_MANUALLY = "done_manually"


class Column(StrEnum):
    """Board columns, in display order."""

    BACKLOG = "backlog"
    RUNNING = "running"
    NEEDS_YOU = "needs_you"
    DONE = "done"


_COLUMNS = {
    Status.BACKLOG: Column.BACKLOG,
    Status.YOURS: Column.BACKLOG,
    Status.CANCELLED: Column.DONE,
    Status.QUEUED: Column.RUNNING,
    Status.WORKING: Column.RUNNING,
    Status.PAUSED_LIMIT: Column.RUNNING,
    Status.SHIPPING: Column.RUNNING,
    Status.WAITING_PHONE_UPDATE: Column.RUNNING,
    Status.NEEDS_YOU: Column.NEEDS_YOU,
    Status.DONE: Column.DONE,
    Status.DONE_MANUALLY: Column.DONE,
}


def column(status: Status) -> Column:
    """Return the board column of a status."""
    return _COLUMNS[status]


def _closed(task: TaskLike, run: RunState | None) -> Status | None:
    """Return the Done or Cancelled status of rules 1, 1a and 1b, None for a card still open."""
    stage = run.stage if run is not None else None
    if stage == MANUAL_STAGE:
        return Status.DONE_MANUALLY
    if task.status == "done" or stage in DONE_STAGES:
        return Status.DONE
    return Status.CANCELLED if task.status == "abandoned" or stage == "cancelled" else None


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
    if (closed := _closed(task, run)) is not None:
        return closed
    if kuhys(task.title, getattr(task, "parts", ())) or (run is None and is_yours(task)):
        return Status.YOURS
    if run is None:
        return Status.BACKLOG
    if run.assignee == "human" and not run.error:
        return Status.YOURS
    if (resting := _resting(run, live)) is not None:
        return resting
    if run.stage in ("shipping", "gate"):  # no card rests at the gate: it ships or closes at once (T2060)
        return Status.SHIPPING
    if run.stage == "paused_limit" or (limit_until is not None and not live):
        return Status.PAUSED_LIMIT
    return Status.WORKING if live or run.stage == "paused_retry" else Status.QUEUED


def _resting(run: RunState, live: bool) -> Status | None:
    """Return NEEDS_YOU when the run waits on kuhy, or WAITING_PHONE_UPDATE when only the phone is missing."""
    if not _needs_you(run, live):
        return None
    pushed = run.stage == "failed" and PHONE in run.extra  # pushed, only the phone update is left
    return Status.WAITING_PHONE_UPDATE if pushed else Status.NEEDS_YOU


def _needs_you(run: RunState, live: bool) -> bool:
    """Rule 6: the run waits on kuhy; paused_retry waits on its own timer, whatever tag it carries."""
    if run.stage == "paused_retry":
        return False
    return (
        run.stage in ("failed", "spec_wait")
        or run.error is not None
        or (run.last_tag in ("Q", "A") and not live)
    )
