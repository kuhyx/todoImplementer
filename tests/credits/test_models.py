"""The credits model is a setting (default Sonnet 5.5) and the cost meter and reserve price the model used."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from todoimpl.credits import live, pacing, prices, route, setting
from todoimpl.credits.meter import Meter
from todoimpl.runner import credit

if TYPE_CHECKING:
    from pathlib import Path

MILLION = {
    "input_tokens": 1_000_000, "output_tokens": 1_000_000,
    "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
}  # fmt: skip


def assistant(msg: str, model: str | None, usage: dict[str, Any]) -> dict[str, Any]:
    message: dict[str, Any] = {"id": msg, "usage": usage, "content": []}
    if model is not None:
        message["model"] = model
    return {"type": "assistant", "message": message}


def use(text: str) -> None:
    path = setting.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def test_t2615_the_credits_model_defaults_to_sonnet_and_is_a_setting() -> None:
    assert setting.model() == "claude-sonnet-5-5"
    use('{"credits_model": "claude-opus-5-5"}')
    assert setting.model() == "claude-opus-5-5"


@pytest.mark.parametrize(
    "text", ['{"credits_model": ""}', '{"credits_model": 5}', '{"credits_model": "x y"}']
)
def test_a_bad_credits_model_means_the_default(text: str) -> None:
    use(text)
    assert setting.model() == "claude-sonnet-5-5"


def test_t2004_an_opus_message_is_priced_at_opus_list_prices() -> None:
    meter = Meter()
    meter.feed(assistant("m1", "claude-opus-5-5", MILLION))
    assert meter.cost() == pytest.approx(4.0 + 20.0 + 0.20 + 5.0)


def test_t2004_a_sonnet_message_keeps_the_sonnet_prices() -> None:
    meter = Meter()
    meter.feed(assistant("m1", "claude-sonnet-5-5", MILLION))
    assert meter.cost() == pytest.approx(3.0 + 15.0 + 0.30 + 3.75)


def test_t2004_a_turn_that_mixes_models_prices_each_message_at_its_own_model() -> None:
    meter = Meter()
    meter.feed(assistant("m1", "claude-sonnet-5-5", {"output_tokens": 1_000_000}))
    meter.feed(assistant("m2", "claude-opus-5-5", {"output_tokens": 1_000_000}))
    assert meter.cost() == pytest.approx(15.0 + 20.0)


def test_t2004_an_unknown_model_is_priced_at_the_dearest_rates_so_the_brake_never_fires_late() -> None:
    meter = Meter()
    meter.feed(assistant("m1", "claude-mystery-9", {"output_tokens": 1_000_000}))
    assert meter.cost() == pytest.approx(20.0)


def test_a_message_without_a_model_is_priced_at_the_configured_credits_model() -> None:
    meter = Meter()
    meter.feed(assistant("m1", None, {"output_tokens": 1_000_000}))
    assert meter.cost() == pytest.approx(15.0)  # the default model is Sonnet
    use('{"credits_model": "claude-opus-5-5"}')
    other = Meter()
    other.feed(assistant("m1", None, {"output_tokens": 1_000_000}))
    assert other.cost() == pytest.approx(20.0)


def test_t2004_the_reserve_scales_with_the_model_price() -> None:
    assert prices.reserve("claude-sonnet-5-5") == pytest.approx(2.0)
    assert prices.reserve("claude-opus-5-5") == pytest.approx(
        4.0
    )  # $20 / $10 output list price, twice Sonnet
    assert prices.reserve("claude-mystery-9") == pytest.approx(4.0)  # unknown: the dearest


def test_t2004_a_running_opus_turn_counts_for_the_opus_reserve(root: Path) -> None:
    use('{"credits_model": "claude-opus-5-5"}')
    live.begin(root, "aaaaaaaa-0")
    live.set_cost(root, "aaaaaaaa-0", 0.5)
    assert pacing.pace(root, 1.0).reserved_usd == pytest.approx(4.0)
    use('{"credits_model": "claude-sonnet-5-5", "credits_monthly_usd": 200, "credits_month_start_day": 1}')
    assert pacing.pace(root, 1.0).reserved_usd == pytest.approx(2.0)


def test_t2004_the_board_text_names_the_model() -> None:
    assert "claude-sonnet-5-5" in route.ready_text()
    assert "opus" not in route.ready_text()


@pytest.mark.parametrize(
    ("wanted", "ran", "held"),
    [
        ("opus", "claude-sonnet-5-5", True),
        ("opus", "claude-opus-5-5", False),
        ("sonnet", "claude-opus-5-5", False),  # an upgrade is not a hold
        ("haiku", "claude-opus-5-5", False),
        ("opus", "claude-mystery-9", True),
    ],
)
def test_a_role_is_held_back_only_when_it_ran_on_a_lesser_model_family(
    wanted: str, ran: str, *, held: bool
) -> None:
    assert credit.downgraded(wanted, ran) is held
