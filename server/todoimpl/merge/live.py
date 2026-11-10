"""Which members have a live run: a merge never closes a note that a session is working on."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board.parse import StateError
from todoimpl.board.state import load, run_dir

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

# Resting stages (DOCS-spec.md) plus shipped: a run in any other stage still owns a session or a worktree.
QUIET = frozenset({"spec_wait", "failed", "paused_limit", "cancelled", "shipped"})


def live_reason(root: Path, ids: Iterable[str]) -> str | None:
    """Return why the first member with a live run blocks the merge, or None when all are quiet."""
    for card_id in ids:
        try:
            run = load(run_dir(root, card_id))
        except StateError:
            return f"{card_id}: its run state is unreadable"
        if run is not None and run.stage not in QUIET:
            return f"{card_id} has a live run ({run.stage})"
    return None
