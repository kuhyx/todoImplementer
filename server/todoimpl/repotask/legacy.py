"""Per-section runs that predate the repo task (DOCS-repotask.md, "Transition from per-section runs")."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.board.parse import StateError
from todoimpl.board.state import load, run_dir

if TYPE_CHECKING:
    from pathlib import Path

# Stages in which an older run still works or waits on its own Ship click: its section stays its own.
ACTIVE = (
    "spec",
    "plan",
    "implement",
    "live_check",
    "checks",
    "shipping",
    "gate",
    "paused_limit",
    "paused_retry",
)
ERROR_CUT = 200


@dataclass(frozen=True)
class Older:
    """What an older run of a section means for the repo task.

    `held`: the run keeps the section and its own card. `note`: where a run that ended left its work.
    """

    held: bool = False
    note: str = ""


def older(root: Path, card: str) -> Older:
    """Return how the older run of this section card counts: held while it works, a note once it rests.

    A run that rests (failed, spec_wait, cancelled) folds into the repo task at once: the section is an
    ordinary part and the repo run is told where the old branch and worktree are. A shipped run closed its
    section. An unreadable state counts as held, so kuhy sees it.
    """
    try:
        run = load(run_dir(root, card))
    except StateError:
        return Older(held=True)
    if run is None or run.stage == "shipped":
        return Older()
    if run.stage in ACTIVE:
        return Older(held=True)
    where = f"branch todo/{card}" + (f", worktree {run.worktree}" if run.worktree else "")
    why = f"; it said: {' '.join(run.error.split())[:ERROR_CUT]}" if run.error else ""
    return Older(note=f"an earlier run ended {run.stage} ({where}){why}")


def in_flight(root: Path, card: str) -> bool:
    """Say whether an older run of this section card is still going (the section keeps its own card)."""
    return older(root, card).held
