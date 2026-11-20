"""What the Scheduler's Start does differently for an umbrella note."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store

from . import store as ustore
from .note import is_umbrella
from .view import child_state

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState


def start_stage(body: str, st: RunState, stage: str) -> str:
    """Return the stage Start puts the run in: an umbrella goes straight to its rounds (no spec, no plan).

    Start also flags the run so the next drive restarts children that failed, were cancelled or asked.
    """
    if not is_umbrella(body):
        return stage
    st.extra["retry_children"] = True
    return "implement"


def forward(run_dir: Path, open_ids: list[str], notes: list[str]) -> None:
    """Hand kuhy's Send notes to every open child's next turn (T2397).

    The umbrella runs no turn of its own once its rounds are over, so a note left in its inbox was never
    taken: every drive ended `failed` and the Scheduler requeued it at once, for ever. The drive now takes
    the inbox each time and treats a note as Retry with the note as the children's brief.
    """
    for cid in open_ids:
        if (st := child_state(run_dir, cid)) is not None:
            st.extra.setdefault("notes", []).extend(notes)
            store.save(ustore.child_dir(run_dir, cid), st)
