"""kuhy picks a model before Start: the pick is only saved, and the Start that follows runs every turn on it.

A card with no run keeps the pick in `<run dir>/pin.json` (`{"model": id}`), never in `model.json`, which
`modelswitch` reads as a pick a live drive has not settled. `Scheduler.start` moves it into the run's pin
(`state.extra.model_pin`), so every way a card starts (the click, errors loop, merge, handoff, triage) takes
it. A resting run (Cancelled, a repo card between cycles) keeps the pick in its own pin at once.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from todoimpl import modelpick
from todoimpl.board.parts import kuhys
from todoimpl.board.status import CYCLE_ENDS
from todoimpl.board.types import MANUAL_REASON
from todoimpl.todo_mcp.model import TodoError

from .files import read_json, write_json

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .scheduler import Scheduler

FILE = "pin.json"
PICKS = tuple(m.id for m in modelpick.MODELS)


def read(directory: Path) -> str | None:
    """Return the model saved before Start, None when there is none (or the file names no known model)."""
    saved: Any = read_json(directory / FILE)
    model = saved.get("model") if isinstance(saved, dict) else None
    return model if model in PICKS else None


def read_card(root: Path, card: str) -> str | None:
    """Return the pick saved for `card` under the run root (the board's `Context.pin`)."""
    return read(root / card)


def save(directory: Path, model: str) -> None:
    """Save the pick; `default` drops it."""
    if model == modelpick.DEFAULT:
        (directory / FILE).unlink(missing_ok=True)
    else:
        write_json(directory / FILE, {"model": model})


def adopt(st: RunState, directory: Path) -> None:
    """Move a pick saved before Start into the run's pin."""
    if (model := read(directory)) is not None:
        st.extra[modelpick.PIN] = model
    (directory / FILE).unlink(missing_ok=True)


def resting(st: RunState | None) -> bool:
    """Tell whether a pick only saves: no run, a cancelled one, or a repo card between cycles."""
    if st is None:
        return True
    if st.closing:
        return False
    return st.stage == "cancelled" or (st.stage in CYCLE_ENDS and bool(st.extra.get("repotask")))


def check(sched: Scheduler, card: str) -> None:
    """Refuse a pick on a card that cannot start: an unknown note, or kuhy's manual work."""
    from .scheduler import RunnerError  # noqa: PLC0415 - scheduler imports this module

    try:
        item = sched.client.get_task(card).item
    except TodoError as exc:
        raise RunnerError(str(exc), "not_found") from exc
    if kuhys(item.title, item.parts):
        raise RunnerError(MANUAL_REASON, "disabled")
