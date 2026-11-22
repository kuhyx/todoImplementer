"""kuhy pins a card to a model (a note naming one, or the picker) and its current stage runs again on it.

The pin is `state.extra.model_pin` (`modelpick.PIN`); `turn._launch` gives it to every turn of the card, on
the plan (`--model`) and on the credits (the SDK's `model`), over the role, tier and escalation models.

- A resting card (gate, failed, a spec wait, a retry pause) goes back to work like a note sends it
  (`Scheduler._route`), its stage again on the new model; a queued or limit-paused card just keeps the pin.
- A live drive is stopped, as Cancel stops it, after the click writes `model.json` (the pin and the stage it
  was in): the drive saves the state it loaded, so the pin is written once the drive has ended (`settle`, from
  `Scheduler.after_drive`), the stage is put back and the card queued. The role's session is kept, so the next
  turn resumes it with `--resume <id> --model <pin>` (claude 2.1.328 switches the model of a resumed session).
- Server start settles a `model.json` a restart left (`recover`).
- A card that has not started (Backlog, Cancelled, a repo card between cycles) only saves the pick; its next
  Start runs on it (`prepin`, T2478).
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

from todoimpl import modelpick
from todoimpl.board import state as store

from . import adopt, prepin
from .files import read_json, write_json

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .scheduler import Scheduler

FILE = "model.json"
NO_PICK = ("shipped", "closed", "cancelled", "done_manually", "shipping")
QUIET = ("paused_limit",)  # resumes by itself; a new pin is all it needs
CUT = "(runner) kuhy moved this card to {model} mid-turn: go on with this stage where you stopped."
REDO = "(runner) kuhy asked for this stage again on {model}: do its work again on it and report as usual."


def pinned(st: RunState) -> str | None:
    """Return the model the card is pinned to, None when the role and tier rules pick."""
    pin = st.extra.get(modelpick.PIN)
    return pin if isinstance(pin, str) and pin else None


def _pin(st: RunState, model: str) -> None:
    if model == modelpick.DEFAULT:
        st.extra.pop(modelpick.PIN, None)
    else:
        st.extra[modelpick.PIN] = model


def _nudge(st: RunState, model: str, text: str) -> None:
    """Tell the next turn (once) why it runs; `default` names no model."""
    st.extra["nudge"] = text.format(model="the default model" if model == modelpick.DEFAULT else model)


def pick(sched: Scheduler, card: str, model: str, note: str = "") -> None:
    """Pin `card` to `model` (an id of `modelpick.IDS`) and run its current stage again on it.

    `note` is the rest of a note that started with the command (T2221): it waits in the inbox for that turn.
    """
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    if model not in modelpick.IDS:
        msg = f"unknown model {model}"
        raise RunnerError(msg, "bad_request")
    if not note and prepin.resting(store.load(sched.root / card)):
        prepin.check(sched, card)  # the note's read stays outside the lock, as in Scheduler.start
    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in stopping.done_manually
        if not note and _saved(sched, card, model):
            return
        st = sched._load(card)  # noqa: SLF001
        if st.stage in NO_PICK or st.closing:
            msg = f"The run is {'closing' if st.closing else st.stage}: no turn to switch"
            raise RunnerError(msg, "disabled")
        if note:  # before the pin and the queue: the rerun turn drains it like any note of kuhy's
            sched.push_note(card, note)
            shown = {"type": "activity", "at": sched.clock(), "kind": "user", "text": note, "tool": None}
            sched.bus.publish(card, shown)
        if card in sched._active:  # noqa: SLF001
            write_json(sched.root / card / FILE, {"model": model, "stage": st.stage})
            sched.kill(card)  # the drive's cancel ends it; `after_drive` then calls `settle`
            return
        _pin(st, model)
        if card not in sched._queue and st.stage not in QUIET:  # noqa: SLF001
            sched._route(st)  # noqa: SLF001
            _nudge(st, model, REDO)
            sched.enqueue(card)
        sched.save(card, st)


def _saved(sched: Scheduler, card: str, model: str) -> bool:
    """Save a pick on a card that has not started, with nothing queued or run; True when it was one."""
    st = store.load(sched.root / card)
    if not prepin.resting(st) or sched.busy(card):
        return False
    if st is None:
        prepin.save(sched.root / card, model)
    else:
        _pin(st, model)
        sched.save(card, st)
    return True


def settle(sched: Scheduler, card: str) -> bool:
    """Pin the card a live pick stopped, put its stage back and queue it; True when there was one."""
    path = sched.root / card / FILE
    wanted: Any = read_json(path)
    if not isinstance(wanted, dict):
        return False
    path.unlink(missing_ok=True)
    st = store.load(sched.root / card)
    if st is None:
        return False
    _pin(st, str(wanted.get("model")))
    if st.stage == "cancelled" or st.stage not in NO_PICK:  # the cut drive rests at cancelled
        st.stage, st.error = str(wanted.get("stage") or st.stage), None
        _nudge(st, str(wanted.get("model")), CUT)
        sched.enqueue(card)
    sched.save(card, st)
    return True


def overlay(directory: Path, run: RunState) -> RunState:
    """Show a pick the cut drive has not settled: its pin, and its stage, not the cut's `cancelled`."""
    wanted: Any = read_json(directory / FILE)
    if not isinstance(wanted, dict):
        return run
    shown = replace(run, extra=dict(run.extra))
    _pin(shown, str(wanted.get("model")))
    if shown.stage == "cancelled" or shown.stage not in NO_PICK:
        shown.stage = str(wanted.get("stage") or shown.stage)
    return shown


def recover(sched: Scheduler) -> None:
    """At server start: settle every pick a restart interrupted, stopping a recovered drive first."""
    with sched._cv:  # noqa: SLF001
        for flag in sorted(sched.root.glob(f"*/{FILE}")):
            card = flag.parent.name
            if card in sched._active:  # noqa: SLF001
                sched.kill(card)
            else:  # a queued drive would adopt the cut turn and go on on the old model
                adopt.abandon(flag.parent)
                settle(sched, card)
