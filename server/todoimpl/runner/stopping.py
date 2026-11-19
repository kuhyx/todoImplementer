"""Ending a run by hand: Cancel (abandons the note) and Done manually (the work is done, no turn runs).

Done manually (T2064, kuhy 2026-11-19) stops any live or queued turn, sends no new one, and rests the run at
stage `done_manually`; the worktree stays, nothing is pushed or deployed. A live drive saves the state it
loaded when its cancel lands, which would overwrite a stage written beside it, so the click writes a file of
its own (`done-manually.json`, like `start-when-free.json`) and the stage is set once the drive has ended
(`settle`, from `Scheduler.after_drive`). Server start settles every file still there (`recover`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.actions import FINAL_STAGES
from todoimpl.board.status import CYCLE_ENDS, DONE_STAGES, MANUAL_STAGE
from todoimpl.todo_mcp.model import TodoError

from . import adopt, modelswitch
from .files import read_json, write_json

if TYPE_CHECKING:
    from pathlib import Path

    from .scheduler import Scheduler

FILE = "done-manually.json"
log = logging.getLogger("todoimpl.runner")


def cancel(sched: Scheduler, card: str) -> None:
    """Cancel click: stop the run, keep its dir, abandon the note when no other section is open."""
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in whenfree.arm
        st = sched._load(card)  # noqa: SLF001
        if st.stage in FINAL_STAGES:
            msg = f"The run is already {st.stage}"
            raise RunnerError(msg, "disabled")
        (sched.root / card / modelswitch.FILE).unlink(missing_ok=True)  # a pending pick must not restart it
        if card in sched._active:  # noqa: SLF001
            sched.kill(card)
        else:
            _leave(sched, card)
            st.stage = "cancelled"
            sched.save(card, st)
            sched.bus.publish(card, {"type": "done"})
    try:  # a cancelled card is abandoned in the todo app too, where a whole note can be (T1815)
        sched.client.abandon(card)
    except TodoError as exc:
        log.warning("cancel %s: the note stays open, the todo app refused: %s", card, exc)


def _leave(sched: Scheduler, card: str) -> None:
    """Take a card that has no live drive out of the queue and stop a turn no drive follows."""
    if card in sched._queue:  # noqa: SLF001
        sched._queue.remove(card)  # noqa: SLF001
        sched.locks.release(card)
    adopt.abandon(sched.root / card)  # a turn no drive follows must not go on editing the worktree


def refusal(stage: str | None, *, repotask: bool) -> str | None:
    """Return why a card at this stage cannot be rested at `done_manually`, None when it can.

    A repo task whose cycle ended (shipped, or done manually) with parts left is a new cycle: it can.
    """
    if stage == "shipping":
        return "shipping cannot be stopped"
    over = stage in (*DONE_STAGES, MANUAL_STAGE)
    return f"The card is already {stage}" if over and not (repotask and stage in CYCLE_ENDS) else None


def done_manually(
    sched: Scheduler, card: str, *, repo: str | None = None, title: str = "", repotask: bool = False
) -> None:
    """Rest the card at `done_manually`; with no run it gets one (`repo`, `title`, `repotask` describe it).

    The notes are closed by the caller first. A live drive is stopped; the stage follows when it has ended.
    """
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    with sched._cv:  # noqa: SLF001
        st = store.load(sched.root / card)
        if st is not None and (msg := refusal(st.stage, repotask=repotask)) is not None:
            raise RunnerError(msg, "disabled")
        write_json(sched.root / card / FILE, {"repo": repo, "title": title, "repotask": repotask})
        (sched.root / card / modelswitch.FILE).unlink(missing_ok=True)
        if card in sched._active:  # noqa: SLF001
            sched.kill(card)  # the drive's cancel ends it; `after_drive` then calls `settle`
        else:
            settle(sched, card)


def settle(sched: Scheduler, card: str) -> bool:
    """Rest a card that kuhy marked done manually; True when it did. Callers hold the Scheduler's lock."""
    path = sched.root / card / FILE
    wanted: Any = read_json(path)
    if not isinstance(wanted, dict):
        return False
    _leave(sched, card)
    st = store.load(sched.root / card) or store.RunState(
        task_id=card, stage=MANUAL_STAGE, started_at=sched.clock(), repo=wanted.get("repo")
    )
    if wanted.get("repotask"):  # ClosedNotes rebuilds the Done card of a repo task from these two
        st.extra.update(repotask=True, repotask_title=wanted.get("title") or st.repo or card)
    st.stage, st.error = MANUAL_STAGE, None
    sched.save(card, st)
    path.unlink(missing_ok=True)
    sched.bus.publish(card, {"type": "done"})
    return True


def pending(root: Path) -> list[str]:
    """Return the cards whose click was taken but not yet settled."""
    return sorted(flag.parent.name for flag in root.glob(f"*/{FILE}"))


def recover(sched: Scheduler) -> None:
    """At server start: settle every click a restart interrupted (the drive that would have is gone)."""
    with sched._cv:  # noqa: SLF001
        for card in pending(sched.root):
            if card in sched._active:  # noqa: SLF001 - a recovered drive is already running: stop it first
                sched.kill(card)
            else:
                settle(sched, card)
