"""May an error card start now? kuhy's rule: weekly plan usage under 80 %, or free credits, or free models.

Checked in that order; the first that holds is the card's `reason`. Anything unknown fails closed: no plan
login, no `seven_day` window or a dead probe is not "under 80 %".
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todoimpl.credits import route
from todoimpl.runner import freegate, limitprobe
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.worktree import repo_dir
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from pathlib import Path

WEEKLY_MAX = 0.80  # the weekly window must be below this fraction


def _credits(root: Path, now: float) -> bool:
    """Say whether the free API credits take a turn right now (fallback ready, the week's pace has room)."""
    return route.choose(root, now).route == route.CREDITS


def _free(repo: str) -> bool:
    """Say whether free models may work on the repo: public, tools present, gateway answering."""
    try:
        return freegate.check(repo_dir(repo)).allowed
    except NeedsYouError:  # not cloned here: nothing to run free models on
        return False


@dataclass
class Gate:
    """The three probes, replaceable in tests; `fetch` asks the plan for its real usage."""

    fetch: Callable[[float], oauth.Probe | None] = oauth.fetch
    credits: Callable[[Path, float], bool] = _credits
    free: Callable[[str], bool] = field(default=_free)

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
        """Return why a card of `repo` may start (`weekly`, `credits` or `free`), or None to wait."""
        if self._weekly(root, now):
            return "weekly"
        if self.credits(root, now):
            return "credits"
        return "free" if self.free(repo) else None
