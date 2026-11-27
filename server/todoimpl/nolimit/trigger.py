"""When the no-limit runner may work: no Claude route can run a turn and the free models have nothing to do.

All three must hold (kuhy, 2026-11-27):

1. the plan is limited: a card rests `paused_limit`, the 95 % weekly hold is on (`usage-hold.json`), or the
   limit mark (`limit-until`) has not lifted;
2. the free API credits take no turn (`credits.route.choose` picks no `credits`: not `ready`, or over cap);
3. the free route is unusable: the gateway is down, or no card waiting on the limit may go free (public repo).

The runner asks again before each step, so it stops the moment any route opens. Never blocks: the gateway
answer is `runner.freeok`'s cached one, the rest are files under the run root.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.credits import route
from todoimpl.runner import freeok
from todoimpl.usage import hold
from todoimpl.usage.limits import limit_state

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from todoimpl.board.state import RunState

PAUSED = "paused_limit"


def _paused(root: Path) -> Iterator[RunState]:
    """Yield every run resting on the plan limit."""
    for directory in sorted(root.iterdir()) if root.is_dir() else []:
        if not (directory / store.FILE).is_file():
            continue
        try:
            st = store.load(directory)
        except StateError:
            continue
        if st is not None and st.stage == PAUSED:
            yield st


def plan_limited(root: Path, now: float) -> bool:
    """Say whether the plan takes no turn now."""
    if hold.level(root, now) == hold.ALL or limit_state(root).active(now):
        return True
    return any(True for _ in _paused(root))


def credits_open(root: Path, now: float) -> bool:
    """Say whether a turn would run on the free API credits now."""
    return route.choose(root, now).route == route.CREDITS


def free_open(root: Path, gateway_up: Callable[[], bool]) -> bool:
    """Say whether a waiting card could go on the free models now."""
    waiting = any(
        freeok.public(st.repo) and freeok.ERROR_LINE not in (st.note_body or "") for st in _paused(root)
    )
    return waiting and gateway_up()


def holds(root: Path, now: float, gateway_up: Callable[[], bool] = freeok.gateway_up) -> bool:
    """Say whether the runner may work now: the plan is limited and no other route is open."""
    return plan_limited(root, now) and not credits_open(root, now) and not free_open(root, gateway_up)
