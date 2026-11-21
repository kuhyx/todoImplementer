"""kuhy's night (22:55-05:55 local): the window, its parsing and the time left to the morning."""

from datetime import datetime

import pytest
from todoimpl import night

ENV = {"TODOIMPL_NIGHT": "22:55-05:55"}


def at(hh: int, mm: int, ss: int = 0) -> datetime:
    return datetime(2026, 11, 21, hh, mm, ss).astimezone()


@pytest.mark.parametrize(
    ("when", "asleep"),
    [
        (at(22, 54, 59), False),
        (at(22, 55), True),
        (at(23, 59), True),
        (at(0, 0), True),
        (at(5, 54, 59), True),
        (at(5, 55), False),
        (at(12, 0), False),
    ],
)
def test_window_wraps_midnight(when: datetime, asleep: bool) -> None:
    assert night.is_night(when, ENV) is asleep


def test_default_window_when_unset() -> None:
    assert night.is_night(at(23, 0), {}) is True
    assert night.is_night(at(9, 0), {}) is False


@pytest.mark.parametrize("raw", ["off", "", "junk", "25:00-05:00", "22:55"])
def test_off_or_malformed_means_never_night(raw: str) -> None:
    assert night.is_night(at(23, 0), {"TODOIMPL_NIGHT": raw}) is False


def test_a_window_inside_one_day() -> None:
    env = {"TODOIMPL_NIGHT": "01:00-03:00"}
    assert night.is_night(at(2, 0), env) is True
    assert night.is_night(at(4, 0), env) is False


@pytest.mark.parametrize(
    ("when", "left"),
    [(at(23, 55), 6 * 3600.0), (at(5, 54), 60.0), (at(12, 0), 0.0)],
)
def test_seconds_to_morning(when: datetime, left: float) -> None:
    assert night.to_morning(when, ENV) == left


def test_now_is_the_default_clock() -> None:
    assert night.is_night(None, {"TODOIMPL_NIGHT": "off"}) is False
    assert night.to_morning(None, {"TODOIMPL_NIGHT": "off"}) == 0.0
