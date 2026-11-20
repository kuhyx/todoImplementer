"""An answer kuhy gave is never asked again in the same cycle (T2376).

A session that asks a choice again (in a later reply, so a new round, T2277) gets kuhy's answer back instead
of a fresh open ask, as long as the answer is still one of its options and was given this cycle. Two
exceptions ask again: a `change` on an approval (the edited deliverable is a new thing to judge) and a new
cycle (asks.json outlives a repo card's cycles, and so do the ids). Screenshots always ask again.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import load

if TYPE_CHECKING:
    from pathlib import Path

    from .parse import Ask

APPROVE = re.compile(r"\s*approved?\b", re.IGNORECASE)  # `approve`, `approve once the gaps are filled`


def is_approve(option: object) -> bool:
    """Return True for an option that approves: it starts with the word `approve`."""
    return bool(APPROVE.match(str(option)))


def cycle(directory: Path) -> int:
    """Return the run's cycle (repotask/cycle.py counts it; a run that never cycled is on 1)."""
    run = load(directory)
    return int(run.extra.get("cycle", 1)) if run is not None else 1


def this_cycle(directory: Path, record: dict[str, Any]) -> bool:
    """Return True when the record was written in the run's current cycle.

    Records written before cycles were stamped count when they are newer than this cycle's plan.md (a new
    cycle deletes it, the plan stage rewrites it).
    """
    if "cycle" in record:
        return bool(record["cycle"] == cycle(directory))
    try:
        return float(record.get("at") or 0) >= (directory / "plan.md").stat().st_mtime
    except OSError:
        return False


def keeps(ask: Ask, record: dict[str, Any] | None, directory: Path) -> bool:
    """Return True when a new round's `ask` keeps kuhy's earlier answer instead of asking again."""
    if ask.type != "choice" or not record or record.get("state") != "answered":
        return False
    answer = record.get("answer")
    if answer not in ask.options:
        return False
    if any(is_approve(o) for o in ask.options) and not is_approve(answer):
        return False
    return this_cycle(directory, record)
