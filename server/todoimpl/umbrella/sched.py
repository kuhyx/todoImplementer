"""What the Scheduler's Start does differently for an umbrella note."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .note import is_umbrella

if TYPE_CHECKING:
    from todoimpl.board.state import RunState


def start_stage(body: str, st: RunState, stage: str) -> str:
    """Return the stage Start puts the run in: an umbrella goes straight to its rounds (no spec, no plan).

    Start also flags the run so the next drive restarts children that failed, were cancelled or asked.
    """
    if not is_umbrella(body):
        return stage
    st.extra["retry_children"] = True
    return "implement"
