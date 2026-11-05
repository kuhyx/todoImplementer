"""Plan-limit marker files the runner writes under the run root."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

UNTIL_FILE = "limit-until"
CREDITS_FILE = "limit-credits"


@dataclass(frozen=True)
class LimitState:
    """`until`: epoch the plan limit lifts (None = unknown); `credits`: "Run on credits" was granted."""

    until: float | None
    credits: bool

    def active(self, now: float) -> bool:
        """Return True while the limit has not lifted yet."""
        return self.until is not None and self.until > now


def limit_state(root: Path) -> LimitState:
    """Read `<root>/limit-until` (epoch seconds) and `<root>/limit-credits`.

    Unreadable or non-finite `limit-until` counts as no limit; the credits file
    counts when it exists and does not say `0` (a bare `touch` grants them).
    """
    until: float | None = None
    try:
        value = float((root / UNTIL_FILE).read_text(encoding="utf-8").strip())
        until = value if math.isfinite(value) else None
    except OSError, ValueError:
        until = None
    try:
        granted = (root / CREDITS_FILE).read_text(encoding="utf-8").strip() != "0"
    except OSError:
        granted = False
    return LimitState(until=until, credits=granted)
