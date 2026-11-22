"""What Start does for a repo task, kept out of the Scheduler."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.status import CYCLE_ENDS

from .cycle import new_cycle

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item


def prepare(st: RunState, item: Item, run_dir: Path, now: float) -> None:
    """Mark the run as a repo task's and begin the next cycle when the last one shipped."""
    if st.stage in CYCLE_ENDS:
        new_cycle(st, run_dir, now)
    st.extra["repotask"] = True
    st.extra["repotask_title"] = item.title
