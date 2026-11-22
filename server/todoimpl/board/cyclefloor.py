"""Where a repo card's current cycle starts: what the card shows is this cycle's, the rest stays on disk.

`repotask/cycle.py` records the floor when the next cycle starts (T2479): the time (`cycle_at`), the newest
activity seq of the cycles before (`cycle_seq`) and the cost they spent (`cycle_cost`). The drawer, the card
sheet and the phone feed show only rows above it; the usage page and the token dashboard keep the whole
history. A run that never cycled has no floor and shows everything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .state import RunState

AT, SEQ, COST = "cycle_at", "cycle_seq", "cycle_cost"


def _number(run: RunState | None, key: str) -> float:
    value: Any = run.extra.get(key) if run is not None else None
    return float(value) if isinstance(value, int | float) else 0.0


def since(run: RunState | None) -> float:
    """Return when the run's current cycle started (0 when it never cycled)."""
    return _number(run, AT)


def seq(run: RunState | None) -> int:
    """Return the newest activity seq of the earlier cycles (0 when it never cycled)."""
    return int(_number(run, SEQ))


def spent(run: RunState) -> float:
    """Return what the current cycle cost so far."""
    return max(0.0, run.cost_usd - _number(run, COST))
