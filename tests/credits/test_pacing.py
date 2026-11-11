"""The monthly credit grant paced by week: period start, week number, cap."""

from __future__ import annotations

from datetime import datetime

import pytest
from todoimpl.credits import pacing, setting


def at(year: int, month: int, day: int, hour: int = 12) -> float:
    """Local wall-clock time as an epoch."""
    return datetime(year, month, day, hour).timestamp()  # noqa: DTZ001


@pytest.mark.parametrize(
    ("now", "start_day", "start"),
    [
        (at(2026, 11, 1, 0), 1, at(2026, 11, 1, 0)),
        (at(2026, 11, 11), 1, at(2026, 11, 1, 0)),
        (at(2026, 11, 3), 15, at(2026, 10, 15, 0)),  # before this month's start day: last month's
        (at(2026, 11, 15, 0), 15, at(2026, 11, 15, 0)),
        (at(2026, 11, 14, 23), 15, at(2026, 10, 15, 0)),
        (at(2027, 1, 10), 20, at(2026, 12, 20, 0)),  # across the year
        (at(2026, 3, 5), 28, at(2026, 2, 28, 0)),  # across a short month
    ],
)
def test_period_starts_at_the_latest_start_day_at_local_midnight(
    now: float, start_day: int, start: float
) -> None:
    assert pacing.period_start(now, start_day) == start


@pytest.mark.parametrize(
    ("day", "week"),
    [(1, 1), (7, 1), (8, 2), (14, 2), (15, 3), (21, 3), (22, 4), (28, 4), (31, 4)],
)
def test_week_boundaries_with_start_day_one(day: int, week: int) -> None:
    now = at(2026, 12, day)
    assert pacing.week_of(now, pacing.period_start(now, 1)) == week


def test_week_counts_from_a_start_day_across_the_month_end() -> None:
    start = pacing.period_start(at(2026, 12, 3), 25)  # Nov 25
    assert start == at(2026, 11, 25, 0)
    assert pacing.week_of(at(2026, 12, 1), start) == 1  # 6 days in
    assert pacing.week_of(at(2026, 12, 2), start) == 2  # 7 days in
    assert pacing.week_of(at(2026, 12, 16), start) == 4  # 21 days in
    assert pacing.week_of(at(2026, 12, 24), start) == 4  # never past 4


def test_cap_is_the_week_share_of_the_monthly_grant() -> None:
    assert [pacing.cap_usd(week, 200.0) for week in (1, 2, 3, 4)] == [50.0, 100.0, 150.0, 200.0]


def test_settings_default_to_the_grant_less_a_margin_from_its_day() -> None:
    assert setting.monthly_usd() == 190.0  # the $200 grant minus $10 so week 4 never goes negative
    assert setting.start_day() == 10  # the grant came on the 10th


def test_settings_read_the_file_and_fall_back_on_garbage() -> None:
    path = setting.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"credits_monthly_usd": 80, "credits_month_start_day": 15}')
    assert (setting.monthly_usd(), setting.start_day()) == (80.0, 15)
    for bad in (
        '{"credits_monthly_usd": "x", "credits_month_start_day": "y"}',
        '{"credits_monthly_usd": -5, "credits_month_start_day": 0}',
        '{"credits_monthly_usd": true, "credits_month_start_day": 29}',
        "{broken",
    ):
        path.write_text(bad)
        assert (setting.monthly_usd(), setting.start_day()) == (190.0, 10)
