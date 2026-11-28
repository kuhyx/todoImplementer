"""Credits are paced: a turn takes them only below the weekly cap; past it the plan, or a wait if limited."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import pytest
from pacefakes import PERIOD, WEEK2, limit, spend
from todoimpl.credits import marks, route, setting

if TYPE_CHECKING:
    from pathlib import Path


def test_under_the_cap_a_turn_takes_the_credits_with_or_without_a_plan_limit(root: Path) -> None:
    spend(root, 40.0, WEEK2 - 3600)
    assert route.choose(root, WEEK2) == route.Choice(route.CREDITS)
    limit(root)
    assert route.choose(root, WEEK2) == route.Choice(route.CREDITS)


def test_view_carries_the_pace_and_the_route_now_chosen(root: Path) -> None:
    spend(root, 40.0, WEEK2 - 3600)
    spend(root, 7.0, WEEK2 - 60, on="plan")  # plan turns are not credit spend
    spend(root, 90.0, PERIOD - 3600)  # last period
    view = route.view(root, WEEK2)
    assert {k: view[k] for k in view if k != "text"} == {
        "enabled": True, "state": "ready", "route": "credits", "period_start": PERIOD, "week": 2,
        "monthly_usd": 200.0, "cap_usd": 100.0, "spent_period_usd": 40.0, "credit_turns_period": 1,
        "remaining_usd": 160.0, "over_cap": False, "running_credit_turns": 0, "cost_factor": 1.0,
        "off_text": None, "batches": {"pending": 0, "est_usd": 0, "oldest_at": None},
    }  # fmt: skip
    assert view["text"]


def test_at_the_cap_the_plan_takes_the_turn(root: Path) -> None:
    spend(root, 100.0, WEEK2 - 3600)
    assert route.choose(root, WEEK2) == route.Choice(route.PLAN)
    view = route.view(root, WEEK2)
    assert (view["over_cap"], view["route"], view["state"]) == (True, "plan", "ready")


def test_at_the_cap_with_the_plan_limited_the_turn_waits_for_the_limit(root: Path) -> None:
    spend(root, 100.0, WEEK2 - 3600)
    until = limit(root)
    assert route.choose(root, WEEK2) == route.Choice(None, until)  # the cap is hard, never a fallback
    assert route.view(root, WEEK2)["route"] is None


def test_the_cap_rises_with_the_week(root: Path) -> None:
    spend(root, 150.0, WEEK2 - 3600)
    assert route.choose(root, WEEK2).route == route.PLAN
    week4 = datetime(2026, 11, 25, 9).timestamp()  # noqa: DTZ001
    assert route.choose(root, week4).route == route.CREDITS  # week 4 cap is the whole $200
    assert route.view(root, week4)["remaining_usd"] == 50.0


def test_remaining_never_goes_below_zero(root: Path) -> None:
    spend(root, 250.0, WEEK2 - 3600)
    assert route.view(root, WEEK2)["remaining_usd"] == 0.0


def test_under_the_cap_but_not_ready_the_plan_takes_it_and_a_limit_makes_it_wait(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    setting.set_enabled(value=False)
    assert route.choose(root, WEEK2) == route.Choice(route.PLAN)
    until = limit(root)
    assert route.choose(root, WEEK2) == route.Choice(None, until)
    setting.set_enabled(value=True)
    marks.mark_exhausted(root, WEEK2 + 900, "Credit balance is too low")  # a real billing error still counts
    assert route.view(root, WEEK2)["state"] == "exhausted"
    assert route.choose(root, WEEK2) == route.Choice(None, until)
    marks.clear_exhausted(root)
    monkeypatch.delenv("TODOIMPL_SDK_PYTHON")
    assert route.choose(root, WEEK2) == route.Choice(None, until)
