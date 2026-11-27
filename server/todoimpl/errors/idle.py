"""Other apps' tickets have the lowest priority: they start only on an idle board (T2582).

kuhy, 2026-11-27: "auto-called issues should have lowest available priority, wait for all other tasks to
finish or for the user to run them manually". The board's own tickets (stalls, slow steps, heavy builds, its
own errors) are not other apps' reports and keep going first (`marks.board_key`).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.board import state as store

from .marks import board_key

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from todoimpl.board.state import RunState

# Stages of a run that is working, queued or paused for a limit; a run resting on kuhy is not busy.
WORKING = ("spec", "plan", "implement", "live_check", "checks", "gate", "shipping", "closing")
BUSY = frozenset((*WORKING, "paused_limit", "paused_retry"))
STALL, BOARD, APP = 0, 1, 2  # the start order of the loop's cards
RUN = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")  # a run dir: a card's, an umbrella child's or an older section's


def app_only(keys: Sequence[str]) -> bool:
    """Say whether every ticket of a card is another app's report (none filed by the board)."""
    return not any(board_key(key) for key in keys)


def _busy(run: RunState) -> bool:
    return run.stage in BUSY and run.error is None and run.last_tag not in ("Q", "A")


def busy(root: Path, mine: str) -> bool:
    """Say whether a run other than `mine` is working, queued or paused for a limit (any run dir counts)."""
    found = [path.name for path in root.iterdir() if RUN.fullmatch(path.name) and path.name != mine]
    return any(_busy(run) for run in store.load_runs(root, found).values())
