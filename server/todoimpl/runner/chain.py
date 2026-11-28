"""The one route chain a turn walks (T2531): the free credits, the plan, the free models, else a wait.

`credits.route` decides credits or plan (or the plan's wait); a run the plan cannot take goes on `free` when
`freeroute.eligible` says its repo is public and the gateway answers. Both the engine's queue (`admits`) and
the pipeline's turn (`choose`, `claim`) ask here, so a card is taken off the queue only when a turn can run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.credits import route
from todoimpl.repotask import files
from todoimpl.usage import hold

from . import freeroute

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState


def _or_free(root: Path, choice: route.Choice, st: RunState | None) -> route.Choice:
    if choice.route is not None or not freeroute.eligible(st) or st is None:
        return choice
    # a repo card's error tickets live in its parts, not in note_body (T2622)
    return choice if files.error_fix(root / st.task_id) else route.Choice(freeroute.FREE)


def _hold(root: Path, now: float, choice: route.Choice, card: str | None) -> route.Choice:
    """Apply the weekly holds: 90 % lets only high cards take the plan, 95 % and the daily allowance none."""
    if choice.route != route.PLAN or card is None:
        return choice
    if not hold.held(root, now, files.priority(root / card)):
        return choice
    return route.Choice(None, hold.until(root, now))


def choose(root: Path, now: float, st: RunState | None, card: str | None = None) -> route.Choice:
    """Return the route a turn of `st` (of `card` with no saved state) would take now; None = it waits."""
    found = st.task_id if st is not None else card
    return _or_free(root, _hold(root, now, route.choose(root, now), found), st)


def claim(root: Path, now: float, card: str, st: RunState | None) -> route.Choice:
    """`route.claim` (counts a credit turn as running), else `free` when the run may go free."""
    return _or_free(root, _hold(root, now, route.claim(root, now, card), card), st)


def admits(root: Path, now: float, card: str) -> bool:
    """Say whether the queue may start `card` now: some route can run its turn."""
    return choose(root, now, store.load(root / card), card).route is not None
