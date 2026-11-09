"""Overage guard: a plan turn that starts spending extra usage (money) is killed at once.

kuhy pays for the Max subscription and nothing else. A `rate_limit_event` with `isUsingOverage: true` on a
plan turn means the next tokens are billed beyond it: the turn is stopped the moment the line is read, runs
pause until the plan window resets, and a board banner says so. The free API credits route cannot use
overage, so only plan turns are watched.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from todoimpl.board.types import fmt_when
from todoimpl.credits import marks

from .limits import FALLBACK_PAUSE, write_until
from .stream import Activity, StreamParser

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FULL = 1.0


def reset_of(obj: dict[str, Any], now: float) -> float:
    """Return when the overflowed plan window resets (latest window at its limit), else a fallback pause."""
    info = obj.get("rate_limit_info")
    info = info if isinstance(info, dict) else {}
    windows = info.get("unifiedWindows")
    found: list[float] = []
    for window in windows.values() if isinstance(windows, dict) else []:
        resets, used = window.get("resetsAt"), window.get("utilization")
        full = window.get("status") == "rejected" or (isinstance(used, int | float) and used >= FULL)
        if full and isinstance(resets, int | float) and resets > now:
            found.append(float(resets))
    top = info.get("resetsAt")
    if not found and info.get("rateLimitType") != "overage" and isinstance(top, int | float) and top > now:
        found.append(float(top))
    return max(found, default=now + FALLBACK_PAUSE)


class OverageGuard(StreamParser):
    """A StreamParser that acts on the first overage event of the turn it reads (sticky: acts once)."""

    def __init__(  # noqa: PLR0913, PLR0917 - the collaborators; all injectable for tests
        self,
        root: Path,
        card: str,
        stop: Callable[[], None],
        announce: Callable[[str], None],
        hit: Callable[[float], None],
        clock: Callable[[], float] = time.time,
    ) -> None:
        """`stop` kills the turn, `announce` writes a feed line, `hit` tells the driver the pause end."""
        super().__init__()
        self._args = (root, card, stop, announce, hit, clock)
        self.until: float | None = None

    def feed(self, line: str) -> list[Activity]:
        """Parse as usual; the first line with `isUsingOverage` triggers the guard."""
        out = super().feed(line)
        if self.until is None and self.result.limit is not None and self.result.limit.using_overage:
            self.until = self._trip(json.loads(line))
            out.append(Activity("error", "overage guard: extra usage started, the turn was stopped"))
        return out

    def _trip(self, obj: dict[str, Any]) -> float:
        root, card, stop, announce, hit, clock = self._args
        now = clock()
        until = reset_of(obj, now)
        text = (
            f"Overage guard: a plan turn of {card} started spending extra usage (money) and was stopped. "
            f"Runs are paused until {fmt_when(until, now)}."
        )
        write_until(root, until)
        marks.raise_alert(root, text, until)
        announce(text)
        hit(until)
        stop()
        return until
