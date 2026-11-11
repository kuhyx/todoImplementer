"""Pace the monthly credit grant by week: the cap rises by a quarter of the grant each week of the period.

The period runs from the latest start day (local midnight) to the next. Week = days since its start divided by
seven plus one, never past 4, so days 22 and later are week 4 and the whole grant is free to spend. Pure maths
on epochs and local wall-clock time; the spend itself comes from `ledger`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from . import ledger, live, setting

if TYPE_CHECKING:
    from pathlib import Path

WEEKS = 4
RESERVE_USD = 2.0  # assumed cost of a credit turn that has started and not yet ended
NEAR_CAP_USD = 20.0  # within this of the cap at most one credit turn runs at a time
DAYS_PER_WEEK = 7


@dataclass(frozen=True)
class Pace:
    """Where the credit spend stands against the weekly cap at one moment."""

    period_start: float
    week: int
    monthly_usd: float
    cap_usd: float
    spent_usd: float
    turns: int
    running: int
    cost_factor: float
    live_usd: float  # what the running credit turns have cost so far (estimate, already scaled)
    reserved_usd: float  # what they may still cost: each counts for at least the reserve

    @property
    def over_cap(self) -> bool:
        """True when no credit turn may start.

        Spend plus the running turns' exposure has reached the cap, or the spend is within `NEAR_CAP_USD` of
        it and a credit turn already runs (one at a time near the cap). Billing lags behind the turns, so many
        turns started at once once ran the grant into an unpaid balance.
        """
        near = self.spent_usd >= self.cap_usd - NEAR_CAP_USD and self.running > 0
        return near or self.spent_usd + self.reserved_usd >= self.cap_usd

    @property
    def hard_stop(self) -> bool:
        """True when the spend plus the live cost of the running turns has reached the cap: stop them."""
        return self.spent_usd + self.live_usd >= self.cap_usd

    @property
    def remaining_usd(self) -> float:
        """The grant left, floored at zero."""
        return max(0.0, self.monthly_usd - self.spent_usd)


def period_start(now: float, start_day: int) -> float:
    """Return the epoch of the latest `start_day` 00:00 local time at or before `now`."""
    moment = datetime.fromtimestamp(now)  # noqa: DTZ006 - local wall-clock time is the point
    year, month = moment.year, moment.month
    if moment.day < start_day:
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    return datetime(year, month, start_day).timestamp()  # noqa: DTZ001 - local midnight


def week_of(now: float, start: float) -> int:
    """Return the week (1 to 4) `now` falls in for a period that began at `start`."""
    days = (datetime.fromtimestamp(now) - datetime.fromtimestamp(start)).days  # noqa: DTZ006
    return min(WEEKS, days // DAYS_PER_WEEK + 1)


def cap_usd(week: int, monthly_usd: float) -> float:
    """Return how much of the grant may be spent by the end of `week`."""
    return week * monthly_usd / WEEKS


def pace(root: Path, now: float) -> Pace:
    """Return the pace at `now` from the settings and the ledger's credit spend since the period began.

    `credits_cost_factor` scales the ledger's SDK cost to the billed one (1.0: they agreed within 1 % on
    2026-11-11), so `spent_usd` is an estimate of the real spend; running turns' live cost is scaled alike.
    """
    monthly = setting.monthly_usd()
    start = period_start(now, setting.start_day())
    week = week_of(now, start)
    factor = setting.cost_factor()
    live_costs = [c * factor for c in live.costs(root)]
    return Pace(
        start, week, monthly, cap_usd(week, monthly), ledger.spent(root, start) * factor,
        ledger.turns(root, start), len(live_costs), factor, sum(live_costs),
        sum(max(c, RESERVE_USD) for c in live_costs),
    )  # fmt: skip
