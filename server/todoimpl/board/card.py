"""One board card: the contract's task_card object, built from a note, its run and the computed status."""

from __future__ import annotations

import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from todoimpl.errors.marks import signatures
from todoimpl.umbrella.note import is_umbrella

from .actions import actions
from .badges import tier_badges
from .needs import needs
from .parts import is_repo_task, kuhys, manual_ask, parts_of
from .status import SHIP_STEP, Status, column, compute
from .types import Limit, fmt_when
from .umbrella import card_view

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from .state import RunState
    from .types import TaskLike


@dataclass(frozen=True)
class Context:
    """Everything outside the note and its run that decides a card: live runs, limit, clock."""

    live: frozenset[str] = frozenset()
    limit: Limit = field(default_factory=Limit)
    now: float = 0.0
    repo_missing: Callable[[str | None], str | None] = lambda _repo: None
    auto_close: bool = False  # settings.json `auto_close`
    checks: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)  # autocheck.json, by item id
    waits: Mapping[str, str] = field(default_factory=dict)  # queued run -> the run of its repo it waits on


def current_line(  # noqa: PLR0911 - one return per status
    status: Status, run: RunState | None, resumes_at: float | None, now: float, *, exhausted: bool = False
) -> str:
    """Return one line on what the task does or waits on (never a second status)."""
    if status == Status.WORKING and run is not None:
        return _working(run)
    if status == Status.QUEUED and run is not None:
        return f"waiting to continue {run.stage}"
    if status == Status.PAUSED_LIMIT:
        if exhausted:
            return "free API credits exhausted" + (
                f", resumes {fmt_when(resumes_at, now)}" if resumes_at else ""
            )
        if run is not None and run.stage == "spec" and any(q.answer for q in run.spec_questions):
            when = f"after {fmt_when(resumes_at, now)}" if resumes_at else "when the limit passes"
            return f"answers saved; Claude continues {when}"
        return "paused by the usage limit" + (f", resumes {fmt_when(resumes_at, now)}" if resumes_at else "")
    if status == Status.NEEDS_YOU and run is not None:
        return needs(run).text
    if status == Status.SHIPPING and run is not None and run.extra.get(SHIP_STEP):
        return f"shipping: {run.extra[SHIP_STEP]}"  # the step the ship is in (T2060)
    return {
        Status.BACKLOG: "not started",
        Status.YOURS: "yours: no repo on this note" if run is None else "assigned to you",
        Status.CANCELLED: "cancelled",
        Status.SHIPPING: "pushing and closing the note",
        Status.WAITING_PHONE_UPDATE: "wait for phone to connect, then update the app",
        Status.DONE: "done",
    }[status]


def _working(run: RunState) -> str:
    """Return the stage line; a run waiting to retry says when and why."""
    if run.stage == "paused_retry":
        at = time.strftime("%H:%M", time.localtime(run.resume_at or 0))
        return f"retrying at {at}: {run.extra.get('retry_reason', 'a failed turn')}"
    return run.stage


def partial_of(run: RunState | None) -> dict[str, Any] | None:
    """Return the contract's partial object (live-check outcome) or None when the run has none."""
    found = run.extra.get("partial") if run is not None else None
    if run is None or not isinstance(found, dict):
        return None
    keys = ("done", "open", "deferred")
    return {key: list(found.get(key, [])) for key in keys} | {"followup_id": run.extra.get("followup_id")}


def _assignee(task: TaskLike, run: RunState | None) -> str:
    """Return the human for a manual note or no repo, else the run's assignee (Claude by default)."""
    if kuhys(task.title, getattr(task, "parts", ())):
        return "human"
    if run is not None:
        return run.assignee
    return "human" if task.repo is None and not is_umbrella(task.body) else "claude"


def build_card(task: TaskLike, run: RunState | None, ctx: Context) -> dict[str, Any]:
    """Return the task_card object for one note."""
    tid = task.id
    spent = 0.0
    if run is not None and run.stage == "shipped" and is_repo_task(task):  # parts are left: the next cycle
        spent, run = run.cost_usd, None
    live = tid in ctx.live
    limit_until = ctx.limit.until if ctx.limit.active else None
    status = compute(task, run, live, limit_until if ctx.limit.holds else None)
    resumes_at = None
    if status == Status.PAUSED_LIMIT:
        resumes_at = run.resume_at if run is not None and run.resume_at else limit_until
    repo_missing = ctx.repo_missing(task.repo) if task.repo else None
    buttons = actions(
        task,
        run,
        status,
        ctx.limit,
        repo_missing=repo_missing,
        now=ctx.now,
        check=ctx.checks.get(tid),
    )
    entry = ctx.checks.get(tid) if ctx.auto_close and status == Status.BACKLOG else None
    card = {
        "id": tid,
        "title": task.title,
        "repo": task.repo,
        "priority": task.priority,
        "assignee": _assignee(task, run),
        "stage": run.stage if run is not None else None,
        "status": status.value,
        "column": column(status).value,
        "current": current_line(
            status, run, resumes_at, ctx.now, exhausted=ctx.limit.credits.state == "exhausted"
        ),
        "needs": needs(run).to_dict() if status == Status.NEEDS_YOU and run is not None else None,
        "partial": partial_of(run),
        "cost_usd": run.cost_usd if run is not None else spent,
        "route": run.extra.get("route") if run is not None else None,
        "tier": tier_badges(task, run),
        "resumes_at": resumes_at,
        "updated": run.updated if run is not None else None,
        "actions": [a.to_dict() for a in buttons],
        "auto_start": run.auto_start if run is not None else None,
        "auto": str(entry["reason"]) if entry is not None else None,
    }
    if status == Status.YOURS and kuhys(task.title, getattr(task, "parts", ())):
        card["current"] = manual_ask(task)  # what kuhy must do, never "no repo" on a card that has one
    if errors := len(signatures(task.body)):  # tickets of the errors loop on this card (a badge)
        card["app_error"] = errors
    if (umbrella := card_view(task, run)) is not None:
        card["umbrella"] = umbrella
    if (parts := parts_of(task, run, working=status == Status.WORKING)) is not None:
        card["parts"] = parts
    if (waits := ctx.waits.get(tid)) is not None and status == Status.QUEUED:
        card["waits_on"] = waits
        card["current"] = ""  # the lock badge names the run it waits on; no stage line (T1925)
    return card
