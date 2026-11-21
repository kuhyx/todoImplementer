"""May an error card start now? kuhy's rule: weekly plan usage under 80 %, or free credits.

Never free models (kuhy, 2026-11-21: "they are too dumb for it", T2445): a card waits for the plan or credits.

Checked in that order; the first that holds is the card's `reason`. Anything unknown fails closed: no plan
login, no `seven_day` window or a dead probe is not "under 80 %".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.credits import route
from todoimpl.runner import limitprobe
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from pathlib import Path

WEEKLY_MAX = 0.80  # the weekly window must be below this fraction


def _credits(root: Path, now: float) -> bool:
    """Say whether the free API credits take a turn right now (fallback ready, the week's pace has room)."""
    return route.choose(root, now).route == route.CREDITS


@dataclass
class Gate:
    """The three probes, replaceable in tests; `fetch` asks the plan for its real usage."""

    fetch: Callable[[float], oauth.Probe | None] = oauth.fetch
    credits: Callable[[Path, float], bool] = _credits

    def _weekly(self, root: Path, now: float) -> bool:
        """Weekly use below the limit, from a probe no older than the probe interval (else read it now)."""
        probe = oauth.load(root)
        if probe is None or now - probe.at > limitprobe.INTERVAL:
            probe = self.fetch(now)
            if probe is not None:
                oauth.save(root, probe)
        week = probe.seven_day if probe is not None else None
        return week is not None and week.utilization < WEEKLY_MAX

    def check(self, root: Path, repo: str, now: float) -> str | None:
        """Return why a card of `repo` may start (`weekly` or `credits`), or None to wait."""
        del repo  # every repo waits the same way; kept so callers name the card's repo
        if self._weekly(root, now):
            return "weekly"
        return "credits" if self.credits(root, now) else None
