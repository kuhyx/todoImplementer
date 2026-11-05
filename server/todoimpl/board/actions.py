"""Buttons per card: listed enabled only when they can succeed now, else disabled with the missing thing."""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .status import Status, needs
from .types import fmt_when

if TYPE_CHECKING:
    from .state import RunState
    from .types import Limit, TaskLike

FINAL_STAGES = ("shipped", "cancelled")


@dataclass(frozen=True)
class Action:
    """One button; `reason` is set exactly when it is disabled."""

    id: str
    label: str
    enabled: bool = True
    reason: str | None = None
    confirm: bool = False
    value: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the contract object (confirm/value only when set)."""
        out: dict[str, object] = {
            "id": self.id,
            "label": self.label,
            "enabled": self.enabled,
            "reason": self.reason,
        }
        if self.confirm:
            out["confirm"] = True
        if self.value is not None:
            out["value"] = self.value
        return out


def _missing(repo_missing: str | None, block: str | None) -> str | None:
    """Return the reason a (re)start cannot succeed: the repo is not on disk, else the launch block."""
    return f"repo {repo_missing} not found" if repo_missing else block


def _start_block(task: TaskLike, block: str | None, repo_missing: str | None) -> str | None:
    """Return why a first start cannot succeed."""
    return "note has no repo" if task.repo is None else _missing(repo_missing, block)


def _gate(label: str, action_id: str, reason: str | None, *, confirm: bool = False) -> Action:
    """Return the action, disabled with `reason` when one is given."""
    return Action(action_id, label, reason is None, reason, confirm)


def launch_block(run: RunState | None, limit: Limit, now: float) -> str | None:
    """Return why a Claude session cannot be launched right now (the usage limit), else None; no run cap."""
    if limit.active and not (run is not None and run.using_credits):
        when = f" until {fmt_when(limit.until, now)}" if limit.until is not None else ""
        return f"usage limit{when}"
    return None


def actions(  # noqa: PLR0913 - the signature of the interface plus keyword-only context
    task: TaskLike,
    run: RunState | None,
    status: Status,
    limit: Limit,
    *,
    repo_missing: str | None = None,
    now: float | None = None,
) -> list[Action]:
    """Return the buttons of a card in display order, each enabled only if it can succeed now."""
    clock = time.time() if now is None else now
    block = launch_block(run, limit, clock)
    out = _primary(task, run, status, block, limit, repo_missing)
    if run is not None and status != Status.DONE:
        out += _session(run, status, block)
    if run is not None and run.lesson and run.lesson.get("state") == "drafted":
        out.append(Action("lesson-approve", "Approve lesson"))
    return out


def _primary(  # noqa: PLR0911, PLR0913, PLR0917 - one branch per status keeps the table readable
    task: TaskLike,
    run: RunState | None,
    status: Status,
    block: str | None,
    limit: Limit,
    repo_missing: str | None,
) -> list[Action]:
    """Return the status-specific buttons (start, spec, ship, credits, cancel)."""
    cancel = Action("cancel", "Cancel", confirm=True)
    if status in (Status.BACKLOG, Status.CANCELLED):
        label = "Restart" if status == Status.CANCELLED else "Start"
        return [_gate(label, "start", _start_block(task, block, repo_missing))]
    if status in (Status.QUEUED, Status.WORKING):
        return [cancel]
    if status == Status.SHIPPING:
        return [Action("cancel", "Cancel", enabled=False, reason="shipping cannot be cancelled")]
    if status == Status.PAUSED_LIMIT:
        return [_credits(run, limit), cancel]
    if status == Status.READY_TO_SHIP:
        return [_gate("Ship", "ship", _ship_block(run), confirm=True), cancel]
    if status == Status.NEEDS_YOU and run is not None:
        return _needs_you(run, block, repo_missing, cancel)
    return []


def _needs_you(run: RunState, block: str | None, repo_missing: str | None, cancel: Action) -> list[Action]:
    """Return the buttons that answer the kind of need."""
    kind = needs(run).kind
    if kind == "spec_questions":
        waiting = len(run.open_questions())
        return [
            _gate("Send answers", "spec-answers", block),
            _gate("Spec OK", "spec-ok", f"{waiting} question(s) still unanswered"),
            cancel,
        ]
    if kind == "spec_ok":
        return [_gate("Spec OK", "spec-ok", block), cancel]
    if kind == "handed_to_you":
        return [_gate("Hand back to Claude", "start", _missing(repo_missing, block)), cancel]
    if kind in ("run_failed", "checks_failed"):
        return [_gate("Retry", "start", _missing(repo_missing, block)), cancel]
    return [cancel]


def _credits(run: RunState | None, limit: Limit) -> Action:
    """Return Run on credits, enabled only while a limit is active and credits can pay."""
    if run is not None and run.using_credits:
        reason: str | None = "already running on credits"
    elif not limit.active:
        reason = "no usage limit is active: the run resumes by itself"
    else:
        reason = None if limit.credits_available else "credits are not available (overage rejected)"
    return _gate("Run on credits", "credits", reason, confirm=True)


def _ship_block(run: RunState | None) -> str | None:
    """Return what stops Ship from succeeding (missing worktree, red checks)."""
    if run is None or not run.worktree:
        return "no worktree to ship"
    if run.checks is not None and not run.checks.get("passed", True):
        return "checks are red"
    return None


def _session(run: RunState, status: Status, block: str | None) -> list[Action]:
    """Return Send to Claude and copy-resume, which depend on the session."""
    out: list[Action] = []
    if run.stage not in FINAL_STAGES and status != Status.YOURS:
        if not run.session_id:
            reason: str | None = "no Claude session yet"
        elif status == Status.WORKING:
            reason = None
        elif status in (Status.QUEUED, Status.SHIPPING):
            reason = "the run is waiting to start" if status == Status.QUEUED else "shipping is in progress"
        else:
            reason = block
        out.append(_gate("Send to Claude", "send", reason))
    if run.session_id:
        out.append(_resume(run))
    return out


def _resume(run: RunState) -> Action:
    """Return the copy-resume button carrying `cd <worktree> && claude --resume <id>`."""
    if not run.worktree:
        return Action("copy-resume", "Copy resume command", enabled=False, reason="no worktree yet")
    value = f"cd {shlex.quote(run.worktree)} && claude --resume {shlex.quote(run.session_id or '')}"
    return Action("copy-resume", "Copy resume command", value=value)
