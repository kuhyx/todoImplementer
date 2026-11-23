"""Buttons per card: listed enabled only when they can succeed now, else disabled with the missing thing."""

from __future__ import annotations

import shlex
import time
from typing import TYPE_CHECKING

from todoimpl import modelpick

from .button import Action
from .needs import needs
from .norepo import is_yours
from .parts import kuhys
from .status import MANUAL_STAGE, Status
from .types import MANUAL_REASON, fmt_when

if TYPE_CHECKING:
    from collections.abc import Mapping
    from typing import Any

    from .state import RunState
    from .types import Limit, TaskLike

FINAL_STAGES = ("shipped", "closed", "cancelled", MANUAL_STAGE)
NO_NOTES = "closing runs take no notes; Start again or Cancel"
ABANDONED = "the note is abandoned: auto close no longer polls its done_check"
DONE = (Status.DONE, Status.DONE_MANUALLY)
PRESTART = (Status.BACKLOG, Status.CANCELLED, Status.YOURS)  # Start or Restart: a pick waits for it (T2478)
WONT = (Status.BACKLOG, Status.CANCELLED, Status.YOURS, Status.NEEDS_YOU)  # no turn runs: Won't do drops it


def _missing(repo_missing: str | None, block: str | None) -> str | None:
    """Return the reason a (re)start cannot succeed: the repo is not on disk, else the launch block."""
    return f"repo {repo_missing} not found" if repo_missing else block


def _start_block(task: TaskLike, block: str | None, repo_missing: str | None) -> str | None:
    """Return why a first start cannot succeed."""
    return "note has no repo" if is_yours(task) else _missing(repo_missing, block)


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
    pin: str | None = None,
) -> list[Action]:
    """Return the buttons of a card in display order, each enabled only if it can succeed now.

    `check` is the card's latest auto-close poll entry; it gates restarting a closing run. `pin` is the
    model kuhy picked before Start (`runner/prepin.py`).
    """
    clock = time.time() if now is None else now
    block = launch_block(limit, clock) or check_block(run, check, task.status)
    out = _primary(task, run, status, block, repo_missing)
    if status in WONT:  # T2045: abandons every note behind the card
        out.append(Action("wont", "Won't do", confirm=True))
    if status not in DONE:  # T2064: kuhy did it himself; the one thing a push in flight cannot take
        why = "shipping cannot be stopped" if status == Status.SHIPPING else None
        out.append(Action("done-manually", "Done manually", why is None, why, confirm=True))
    if run is not None and status not in DONE:
        out += _session(run, status) + _model(run, status)
    out += _prestart(out, run, status, pin)
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
    if status == Status.YOURS and kuhys(task.title, getattr(task, "parts", ())):
        return [Action("start", "Start", enabled=False, reason=MANUAL_REASON)]
    if status == Status.YOURS and run is None and is_yours(task):  # T2092: kuhy can start any note
        return [Action("start", "Start", block is None, block)]
    if status in (Status.BACKLOG, Status.CANCELLED):
        label = "Restart" if status == Status.CANCELLED else "Start"
        reason = _start_block(task, block, repo_missing)
        return [Action("start", label, reason is None, reason)]
    if status in (Status.QUEUED, Status.WORKING):
        return [cancel]
    if status == Status.SHIPPING:
        return [Action("cancel", "Cancel", enabled=False, reason="shipping cannot be cancelled")]
    if status == Status.PAUSED_LIMIT:
        return [cancel]
    if status == Status.WAITING_PHONE_UPDATE:  # Retry deploys now, the phone watcher does it when it attaches
        return [_gate("Retry", "start", _missing(repo_missing, block)), cancel]
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


def _session(run: RunState, status: Status) -> list[Action]:
    """Return Send to Claude and copy-resume, which depend on the session.

    Send takes a note on every open card but a closing one, session or not (T2528): it waits in the inbox
    for the next turn, a usage limit included; a note sent while the card ships reopens it (latenote.py).
    """
    out: list[Action] = []
    if run.stage not in FINAL_STAGES and status != Status.YOURS:
        out.append(_gate("Send to Claude", "send", NO_NOTES if run.closing else None))
    if run.session_id:
        out.append(_resume(run))
    return out


def current_model(run: RunState) -> str | None:
    """Return the picker id of kuhy's pin, else of the model the latest turn ran on (None before any turn)."""
    model = run.extra.get(modelpick.PIN) or run.extra.get("last_model")
    return modelpick.resolve(model) if isinstance(model, str) and model else None


def _model(run: RunState, status: Status) -> list[Action]:
    """Return the model picker (modelswitch): it presses the model the card runs on and reruns on a pick."""
    if run.stage in FINAL_STAGES or run.closing or status == Status.YOURS:
        return []
    why = "shipping is in progress" if status == Status.SHIPPING else None
    value = current_model(run) or modelpick.DEFAULT_MODEL
    return [Action("model", "Model", why is None, why, value=value, choices=tuple(modelpick.choices()))]


def _prestart(out: list[Action], run: RunState | None, status: Status, pin: str | None) -> list[Action]:
    """Return the picker beside an enabled Start or Restart: a pick only saves the model Start runs on."""
    start = next((a for a in out if a.id == "start"), None)
    if status not in PRESTART or start is None or not start.enabled or any(a.id == "model" for a in out):
        return []
    saved = run.extra.get(modelpick.PIN) if run is not None else None
    value = saved if isinstance(saved, str) and saved else pin or modelpick.DEFAULT_MODEL
    return [Action("model", "Model", value=modelpick.resolve(value), choices=tuple(modelpick.choices()))]


def _resume(run: RunState) -> Action:
    """Return the copy-resume button carrying `cd <worktree> && claude --resume <id>`."""
    if not run.worktree:
        why = "closing runs have no worktree" if run.closing else "no worktree yet"
        return Action("copy-resume", "Copy resume command", enabled=False, reason=why)
    value = f"cd {shlex.quote(run.worktree)} && claude --resume {shlex.quote(run.session_id or '')}"
    return Action("copy-resume", "Copy resume command", value=value)
