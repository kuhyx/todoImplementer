"""Helpers of the pacing tests: fixed moments, a ledger spend, a plan limit."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from todoimpl.credits import ledger

if TYPE_CHECKING:
    from pathlib import Path

WEEK2 = datetime(2026, 11, 8, 12).timestamp()  # noqa: DTZ001 - day 8 of a period starting the 1st: week 2, cap 100 of 200
PERIOD = datetime(2026, 11, 1).timestamp()  # noqa: DTZ001


def spend(root: Path, usd: float, at: float, *, on: str = "credits") -> None:
    """Put one finished turn of `usd` into the ledger."""
    ledger.record(
        root, task="abcd1234-0", stem=f"implement-{at:.3f}", role="implement", route=on,
        session_id=None, cumulative=usd, ended_at=at,
    )  # fmt: skip


def limit(root: Path) -> float:
    """Start a plan limit that lasts ten minutes; return its end."""
    until = WEEK2 + 600
    (root / "limit-until").write_text(str(until))
    return until
