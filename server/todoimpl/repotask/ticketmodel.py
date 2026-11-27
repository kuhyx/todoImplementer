"""Other apps' error tickets run on Sonnet 5.5 (kuhy, 2026-11-27: "run on Sonnet 5.5", T2582).

A run whose open parts are all other apps' reports (`repotask/lane.py`, lane `app`) records
`state.extra.ticket_model`; every turn then runs it on every route (credits too), like a pin but below
kuhy's own pick (`model_pin`) and never shown as his. A kuhy or board part still open runs the default model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from . import files, lane

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

MODEL: Final = "claude-sonnet-5-5"
KEY: Final = "ticket_model"


def for_item(item: Item, run_dir: Path | None = None) -> str | None:
    """Return Sonnet when the parts still owed (else all of them) are only other apps' reports."""
    owed = files.unticked(run_dir, item) if run_dir is not None and item.parts else []
    return MODEL if lane.first(owed or item.parts, item.body) == lane.APP else None


def for_card(card: object) -> str | None:
    """Return the model an unstarted card of only other apps' reports runs on (the picker presses it)."""
    return MODEL if lane.of_card(card) == lane.APP else None


def mark(st: RunState, item: Item, run_dir: Path | None) -> None:
    """Record (or drop) the ticket model before a turn."""
    if (model := for_item(item, run_dir)) is not None:
        st.extra[KEY] = model
    else:
        st.extra.pop(KEY, None)


def of(st: RunState) -> str | None:
    """Return the ticket model a run recorded, None when it has none."""
    value = st.extra.get(KEY)
    return value if isinstance(value, str) and value else None
