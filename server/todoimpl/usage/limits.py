"""Plan-limit marker file the runner writes under the run root."""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

UNTIL_FILE = "limit-until"


@dataclass(frozen=True)
class LimitState:
    """`until`: epoch the plan limit lifts (None = unknown or no limit)."""

    until: float | None

    def active(self, now: float) -> bool:
        """Return True while the limit has not lifted yet."""
        return self.until is not None and self.until > now


def limit_state(root: Path) -> LimitState:
    """Read `<root>/limit-until` (epoch seconds); unreadable or non-finite counts as no limit."""
    until: float | None = None
    try:
        value = float((root / UNTIL_FILE).read_text(encoding="utf-8").strip())
        until = value if math.isfinite(value) else None
    except OSError, ValueError:
        until = None
    return LimitState(until=until)
