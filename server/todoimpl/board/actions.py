"""Buttons per card: listed enabled only when they can succeed now, else disabled with the missing thing."""

from __future__ import annotations

import shlex
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.umbrella.note import is_umbrella

from .needs import needs
from .status import Status
from .types import MANUAL_REASON, fmt_when, is_manual

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from .state import RunState
    from .types import Limit, TaskLike

FINAL_STAGES = ("shipped", "closed", "cancelled")
NO_NOTES = "closing runs take no notes; Start again or Cancel"
ABANDONED = "the note is abandoned: auto close no longer polls its done_check"
AUTO_SHIP = "Auto-ship when checks pass"


@dataclass(frozen=True)
class Option:
    """A checkbox sent with its action's click; `reason` is set exactly when it is disabled."""

    id: str
    label: str
    enabled: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class Action:
    """One button; `reason` is set exactly when it is disabled."""

    id: str
    label: str
    enabled: bool = True
    reason: str | None = None
    confirm: bool = False
    value: str | None = None
    option: Option | None = None

    def to_dict(self) -> dict[str, object]:
        """Return the contract object (confirm/value/option only when set)."""
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
        if self.option is not None:
            out["option"] = vars(self.option).copy()
        return out


def _missing(repo_missing: str | None, block: str | None) -> str | None:
    """Return the reason a (re)start cannot succeed: the repo is not on disk, else the launch block."""
    return f"repo {repo_missing} not found" if repo_missing else block


def _start_block(task: TaskLike, block: str | None, repo_missing: str | None) -> str | None:
    """Return why a first start cannot succeed."""
    return (
        "note has no repo"
        if task.repo is None and not is_umbrella(task.body)
        else _missing(repo_missing, block)
    )


def _gate(label: str, action_id: str, reason: str | None, *, confirm: bool = False) -> Action:
    """Return the action, disabled with `reason` when one is given."""
    return Action(action_id, label, reason is None, reason, confirm)


def launch_block(limit: Limit, now: float) -> str | None:
    """Return why a Claude session cannot be launched right now (the usage limit), else None; no run cap."""
    if limit.holds:
        when = f" until {fmt_when(limit.until, now)}" if limit.until is not None else ""
        return f"usage limit{when}" + (f"; {limit.credits.text}" if limit.credits.enabled else "")
    return None


def check_block(
    run: RunState | None, check: Mapping[str, Any] | None, note_status: str = "todo"
) -> str | None:
    """Return why a closing run cannot restart: its done_check is not passing in the latest poll."""
    if run is None or not run.closing:
        return None
    if note_status == "abandoned":  # Cancel abandons the note, and the poll covers open notes only
        return ABANDONED
    if check is None:
        return "done_check not polled (auto close is off, or the first tick has not run)"
    return None if check.get("passed") else f"done_check is not passing: {check.get('reason')}"


def actions(  # noqa: PLR0913 - the signature of the interface plus keyword-only context
    task: TaskLike,
    run: RunState | None,
    status: Status,
    limit: Limit,
    *,
    repo_missing: str | None = None,
    now: float | None = None,
    check: Mapping[str, Any] | None = None,
) -> list[Action]:
    """Return the buttons of a card in display order, each enabled only if it can succeed now.

    `check` is the card's latest auto-close poll entry; it gates restarting a closing run.
    """
    clock = time.time() if now is None else now
    block = launch_block(limit, clock) or check_block(run, check, task.status)
    out = _primary(task, run, status, block, repo_missing)
    if run is not None and status != Status.DONE:
        out += _session(run, status, block)
    if run is not None and run.lesson and run.lesson.get("state") == "drafted":
        out.append(Action("lesson-approve", "Approve lesson"))
    return out


def _primary(  # noqa: PLR0911 - one branch per status keeps the table readable
    task: TaskLike,
    run: RunState | None,
    status: Status,
    block: str | None,
    repo_missing: str | None,
) -> list[Action]:
    """Return the status-specific buttons (start, spec, ship, cancel)."""
    cancel = Action("cancel", "Cancel", confirm=True)
    if status == Status.YOURS and is_manual(task.title):
        return [Action("start", "Start", enabled=False, reason=MANUAL_REASON)]
    if status in (Status.BACKLOG, Status.CANCELLED):
        label = "Restart" if status == Status.CANCELLED else "Start"
        reason = _start_block(task, block, repo_missing)
        return [Action("start", label, reason is None, reason, option=_auto_ship(task))]
    if status in (Status.QUEUED, Status.WORKING):
        return [cancel]
    if status == Status.SHIPPING:
        return [Action("cancel", "Cancel", enabled=False, reason="shipping cannot be cancelled")]
    if status == Status.PAUSED_LIMIT:
        return [cancel]
    if status == Status.READY_TO_SHIP:
        return [_gate("Ship", "ship", _ship_block(run), confirm=True), cancel]
    if status == Status.READY_TO_CLOSE:
        return [Action("close", "Close", confirm=True), cancel]
    if status == Status.NEEDS_YOU and run is not None:
        return _needs_you(run, block, repo_missing, cancel)
    return []


def _needs_you(run: RunState, block: str | None, repo_missing: str | None, cancel: Action) -> list[Action]:
    """Return the buttons that answer the kind of need.

    Answers and Spec OK only store a decision; the turn they release waits in the queue through a usage limit,
    so the limit never disables them.
    """
    kind = needs(run).kind
    if kind == "spec_questions":
        waiting = len(run.open_questions())
        return [
            Action("spec-answers", "Send answers"),
            _gate("Spec OK", "spec-ok", f"{waiting} question(s) still unanswered"),
            cancel,
        ]
    if kind == "spec_ok":
        return [Action("spec-ok", "Spec OK"), cancel]
    if kind == "handed_to_you":
        return [_gate("Hand back to Claude", "start", _missing(repo_missing, block)), cancel]
    if kind == "permission":
        return _permission(run, block, cancel)
    if kind in ("run_failed", "checks_failed"):
        return [_gate("Retry", "start", _missing(repo_missing, block)), cancel]
    return [cancel]


def _auto_ship(task: TaskLike) -> Option:
    """Return the Auto-ship checkbox of Start/Restart: only a done_check note can ship itself."""
    if task.done_check is None and not is_umbrella(task.body):  # an umbrella's children bring their own
        return Option("auto_ship", AUTO_SHIP, enabled=False, reason="the note has no done_check")
    return Option("auto_ship", AUTO_SHIP)


def _permission(run: RunState, block: str | None, cancel: Action) -> list[Action]:
    """Go runs the one-liner and reruns; Copy and Done-rerun cover a terminal command; no command = Retry."""
    perm = run.extra.get("permission")
    perm = perm if isinstance(perm, dict) else {}
    command = perm.get("command")
    if not command:
        return [_gate("Retry", "start", block), cancel]
    tty = bool(perm.get("tty"))
    go = _gate("Go", "go", "needs a terminal: copy it" if tty else block)
    return [go, Action("copy-fix", "Copy", value=command), _gate("Done, rerun", "rerun", block), cancel]


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
        if run.closing:
            reason: str | None = NO_NOTES
        elif not run.session_id:
            reason = "no Claude session yet"
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
        why = "closing runs have no worktree" if run.closing else "no worktree yet"
        return Action("copy-resume", "Copy resume command", enabled=False, reason=why)
    value = f"cd {shlex.quote(run.worktree)} && claude --resume {shlex.quote(run.session_id or '')}"
    return Action("copy-resume", "Copy resume command", value=value)
