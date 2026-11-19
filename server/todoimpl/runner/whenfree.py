"""Moved work starts on an event: a handoff onto a held repo card starts its next cycle when Ship completes.

kuhy (2026-11-18): a session moved to the board (POST /api/sessions/handoff) lands as a part on the repo's one
card. When that card is held (a run working, on spec questions, paused or shipping), its
Start is refused. Instead of waiting for a click, the handoff arms `<run dir>/start-when-free.json`; when that
run ships and the card is back in Backlog, the Scheduler presses Start itself, like a click (no auto-ship).
Cards with no pending handoff keep "never starts by itself" (DOCS-repotask.md, Cycles).

The flag is a file of its own, not a key in state.json: a live drive saves the state it loaded and would drop
a key written beside it. It is written durably, and server start looks for it again (`recover`), so the deploy
restart that Ship itself causes cannot lose it. A Start that begins a new run or cycle drops it (`clear`); a
Retry of a failed run keeps it, so the handed-off work still starts when that run ships.
"""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError

from . import retry
from .files import write_json

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .scheduler import Scheduler

FILE = "start-when-free.json"
FREE = (
    "failed",
    "cancelled",
    "shipped",
)  # Start takes a card resting here (scheduler.RESTARTABLE + a cycle end)
log = logging.getLogger("todoimpl.runner")


def armed(run_dir: Path) -> bool:  # noqa: D103
    return (run_dir / FILE).is_file()


def write(run_dir: Path, now: float) -> None:
    """Arm the flag (durably: it must outlive the restart a Ship's deploy causes)."""
    write_json(run_dir / FILE, {"armed_at": now})


def clear(run_dir: Path) -> None:  # noqa: D103
    (run_dir / FILE).unlink(missing_ok=True)


def arm(sched: Scheduler, card: str) -> bool:
    """Arm the card's Start for the moment its run ships; False when nothing holds it (Start takes it now).

    One step under the Scheduler's lock: a run that ships between the refused Start and this call is seen
    here as free, so no flag is left behind that no event would consume.
    """
    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in closing.auto_start
        st = store.load(sched.root / card)
        if st is None or (st.stage in FREE and not sched.busy(card)):
            return False
        write(sched.root / card, sched.clock())
    return True


def _due(run_dir: Path, st: RunState | None) -> bool:
    return st is not None and st.stage == "shipped" and armed(run_dir)


def after_drive(sched: Scheduler, card: str, st: RunState) -> None:
    """Start the next cycle when the drive that ended shipped and a handoff waits; callers hold the lock."""
    if _due(sched.root / card, st):
        spawn(sched, card)


def recover(sched: Scheduler) -> None:
    """At server start: release every card whose Ship completed while no server was there to see it."""
    for flag in sorted(sched.root.glob(f"*/{FILE}")):
        try:
            st = store.load(flag.parent)
        except StateError:
            continue
        if _due(flag.parent, st):
            spawn(sched, flag.parent.name)


def release(sched: Scheduler, card: str) -> None:
    """Press Start; a refusal drops the flag unless the todo app was only unreachable (a restart retries)."""
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    try:
        sched.start(card)
    except RunnerError as exc:
        if not retry.is_transient(exc.message):
            clear(sched.root / card)  # every part shipped, or kuhy started it meanwhile
        log.warning("start-when-free %s: Start refused: %s", card, exc.message)
        return
    log.info("start-when-free %s: its Ship completed, the handed-off work started", card)


def spawn(sched: Scheduler, card: str) -> None:
    """Release in a thread: Start reads the todo app, which must not happen under the Scheduler's lock."""
    threading.Thread(target=release, args=(sched, card), name=f"whenfree-{card}", daemon=True).start()
