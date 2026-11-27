"""The board's own worktrees, as the no-limit chores see them: ended, waiting or busy.

A run dir `<run root>/<card>` with `state.json` and a worktree (`state.worktree`, a directory with a `.git`
file) is one card tree. Ended: its stage is final (shipped, closed, done manually, cancelled), so the next
Start makes a fresh worktree (`runner.worktree.add`). Busy: a turn is in flight (`turn.pid` exists), never
touched. Waiting: every other one, the cards whose next turn the chores prepare.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from todoimpl.board import state as board_state
from todoimpl.board.parse import StateError
from todoimpl.board.status import CYCLE_ENDS, DONE_STAGES
from todoimpl.runner import orphans

ENDED = frozenset({*DONE_STAGES, *CYCLE_ENDS, "cancelled"})


@dataclass(frozen=True)
class Card:
    """One card that holds a board worktree."""

    id: str
    run_dir: Path
    worktree: Path
    branch: str | None
    stage: str
    base: str  # origin's branch the worktree started from, e.g. `main`
    repo: str  # `owner/name`, else the card id

    @property
    def ended(self) -> bool:
        """Say whether the card's run is over (its worktree is only disk now)."""
        return self.stage in ENDED

    @property
    def busy(self) -> bool:
        """Say whether a turn is in flight (its turn record exists)."""
        return orphans.read(self.run_dir) is not None


def _card(run_dir: Path) -> Card | None:
    try:
        st = board_state.load(run_dir)
    except StateError:
        return None
    if st is None or not st.worktree:
        return None
    tree = Path(st.worktree)
    if not (tree / ".git").exists():
        return None
    found = st.extra.get("base_branch")
    base = found if isinstance(found, str) else "main"
    return Card(st.task_id, run_dir, tree, st.branch, st.stage, base, st.repo or st.task_id)


def all_cards(root: Path) -> list[Card]:
    """Return every card of the run root that holds a worktree, by id."""
    if not root.is_dir():
        return []
    found = (_card(d) for d in sorted(root.iterdir()) if (d / board_state.FILE).is_file())
    return [card for card in found if card is not None]


def waiting(root: Path) -> list[Card]:
    """Return the cards whose next turn has not started: not ended, no turn in flight."""
    return [card for card in all_cards(root) if not card.ended and not card.busy]
