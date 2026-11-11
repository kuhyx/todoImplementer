"""Credit cap guard: the stream follower of a credit turn that adds up its cost as events arrive.

Like the overage guard (`guard.py`, which watches plan turns), it acts the moment a line is read. Every
assistant message moves the turn's live cost (`credits.meter`); `credits.route.watch` compares the period's
spend plus the live cost of all running credit turns with the weekly cap and, at the cap, stops them all
through the hooks `runner.turn` attached. The stop is not a failure: `pipeline.turn` goes on at once on the
plan route, resuming the same session.
"""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from todoimpl.credits import route
from todoimpl.credits.meter import Meter

from .stream import Activity, StreamParser

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

STOPPED = (
    "credit cap: the free credits reached this week's cap, so the turn was stopped and goes on at the plan"
)


class CreditGuard(StreamParser):
    """A StreamParser that keeps the turn's live cost and trips the weekly cap."""

    def __init__(self, root: Path, card: str, clock: Callable[[], float] = time.time) -> None:
        """`root` and `card` key the live registry; `clock` is injectable for tests."""
        super().__init__()
        self._root, self._card, self._clock = root, card, clock
        self._meter = Meter()
        self._said = False

    def feed(self, line: str) -> list[Activity]:
        """Parse as usual; every assistant message updates the live cost and may stop the turns."""
        out = super().feed(line)
        if '"assistant"' not in line:
            return out
        try:
            event = json.loads(line)
        except ValueError:
            return out
        if not self._meter.feed(event):
            return out
        self.result.live_usd = self._meter.cost()
        if route.watch(self._root, self._card, self.result.live_usd, self._clock()) and not self._said:
            self._said = True
            out.append(Activity("error", STOPPED))
        return out
