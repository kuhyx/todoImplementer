"""The one route chain a turn walks (T2531): the free credits, the plan, the free models, else a wait.

`credits.route` decides credits or plan (or the plan's wait); a run the plan cannot take goes on `free` when
`freeroute.eligible` says its repo is public and the gateway answers. Both the engine's queue (`admits`) and
the pipeline's turn (`choose`, `claim`) ask here, so a card is taken off the queue only when a turn can run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.credits import route

from . import freeroute

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState


def _or_free(choice: route.Choice, st: RunState | None) -> route.Choice:
    return route.Choice(freeroute.FREE) if choice.route is None and freeroute.eligible(st) else choice


def choose(root: Path, now: float, st: RunState | None) -> route.Choice:
    """Return the route a turn of `st` would take now; `route` None = it waits until `until`."""
    return _or_free(route.choose(root, now), st)


def claim(root: Path, now: float, card: str, st: RunState | None) -> route.Choice:
    """`route.claim` (counts a credit turn as running), else `free` when the run may go free."""
    return _or_free(route.claim(root, now, card), st)


def admits(root: Path, now: float, card: str) -> bool:
    """Say whether the queue may start `card` now: some route can run its turn."""
    return choose(root, now, store.load(root / card)).route is not None
