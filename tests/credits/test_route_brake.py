"""The start gate and the hard stop: a reserve per running turn, one at a time near the cap, cut at it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pacefakes import WEEK2, spend
from todoimpl.credits import live, route, setting

if TYPE_CHECKING:
    from pathlib import Path


def test_the_ledger_cost_is_scaled_to_the_billed_cost_by_the_factor(root: Path) -> None:
    setting.settings_path().write_text('{"credits_monthly_usd": 200, "credits_month_start_day": 1}')
    assert setting.cost_factor() == 1.0  # the ledger matched the Console bill within 1 %
    setting.settings_path().write_text(
        '{"credits_monthly_usd": 200, "credits_month_start_day": 1, "credits_cost_factor": 0.47}'
    )
    spend(root, 200.0, WEEK2 - 3600)  # $94 billed: under the $100 cap
    view = route.view(root, WEEK2)
    assert (view["spent_period_usd"], view["cost_factor"], view["over_cap"]) == (94.0, 0.47, False)
    spend(root, 20.0, WEEK2 - 1800)  # $103.4 billed
    assert route.choose(root, WEEK2).route == route.PLAN
    for bad in (
        '{"credits_cost_factor": 0}',
        '{"credits_cost_factor": "x"}',
        '{"credits_cost_factor": true}',
    ):
        setting.settings_path().write_text(bad)
        assert setting.cost_factor() == 1.0


def test_each_running_credit_turn_reserves_two_dollars_of_the_cap(root: Path) -> None:
    spend(root, 78.0, WEEK2 - 3600)  # not within $20 of the cap: only the reserve counts
    for n in range(10):
        live.begin(root, f"card{n:04d}-0")
    assert route.choose(root, WEEK2).route == route.CREDITS  # 78 + 10 x 2 < 100
    live.begin(root, "card0010-0")  # 78 + 11 x 2 >= 100: no credit turn may start
    assert route.choose(root, WEEK2).route == route.PLAN
    view = route.view(root, WEEK2)
    assert (view["running_credit_turns"], view["over_cap"], view["spent_period_usd"]) == (11, True, 78.0)
    live.end(root, "card0010-0")
    assert route.choose(root, WEEK2).route == route.CREDITS


def test_a_running_turn_that_cost_more_than_the_reserve_counts_what_it_cost(root: Path) -> None:
    spend(root, 70.0, WEEK2 - 3600)
    live.begin(root, "aaaaaaaa-0")
    assert route.choose(root, WEEK2).route == route.CREDITS  # 70 + reserve 2
    live.set_cost(root, "aaaaaaaa-0", 31.0)  # 70 + 31 >= 100
    assert route.choose(root, WEEK2).route == route.PLAN


def test_within_twenty_dollars_of_the_cap_one_credit_turn_runs_at_a_time(root: Path) -> None:
    spend(root, 80.0, WEEK2 - 3600)  # $20 from the $100 cap
    assert route.claim(root, WEEK2, "aaaaaaaa-0") == route.Choice(route.CREDITS)  # the first one runs
    assert route.claim(root, WEEK2, "bbbbbbbb-0") == route.Choice(route.PLAN)  # a second one goes to the plan
    assert live.running(root) == 1  # a plan turn reserves nothing
    live.end(root, "aaaaaaaa-0")
    assert route.claim(root, WEEK2, "bbbbbbbb-0") == route.Choice(route.CREDITS)


def test_further_than_twenty_dollars_from_the_cap_credit_turns_run_side_by_side(root: Path) -> None:
    spend(root, 79.0, WEEK2 - 3600)
    assert route.claim(root, WEEK2, "aaaaaaaa-0").route == route.CREDITS
    assert route.claim(root, WEEK2, "bbbbbbbb-0").route == route.CREDITS
    assert live.running(root) == 2


def test_the_hard_stop_cuts_every_running_credit_turn_when_spend_plus_live_cost_reaches_the_cap(
    root: Path,
) -> None:
    spend(root, 60.0, WEEK2 - 3600)
    log: list[str] = []
    for card in ("aaaaaaaa-0", "bbbbbbbb-0"):
        live.begin(root, card)
        live.attach(root, card, lambda c=card: log.append(f"hit {c}"), lambda c=card: log.append(f"stop {c}"))  # type: ignore[misc]
    assert route.watch(root, "aaaaaaaa-0", 25.0, WEEK2) is False  # 60 + 25 < 100
    assert route.watch(root, "bbbbbbbb-0", 10.0, WEEK2) is False  # 60 + 35 < 100
    assert log == []
    assert route.watch(root, "aaaaaaaa-0", 30.0, WEEK2) is True  # 60 + 40 >= 100: both stop
    assert sorted(log) == ["hit aaaaaaaa-0", "hit bbbbbbbb-0", "stop aaaaaaaa-0", "stop bbbbbbbb-0"]


def test_the_hard_stop_has_nothing_to_cut_for_a_turn_without_hooks(root: Path) -> None:
    spend(root, 99.0, WEEK2 - 3600)
    assert route.watch(root, "aaaaaaaa-0", 5.0, WEEK2) is False
