from __future__ import annotations

import json
from pathlib import Path

import pytest
from todoimpl.tokens import prices

BOOK = prices.PriceBook(
    models={
        "claude-opus-5": prices.Price(input=5.0, output=25.0, cache_read=0.5),
        "claude-opus-5-5": prices.Price(input=4.0, output=20.0, cache_read=0.2),
    },
    default="claude-opus-5",
)


def _cost(usage: dict[str, int]) -> float:
    return prices.price_of("claude-opus-5", usage, BOOK)


def test_for_model_exact_prefix_and_default() -> None:
    assert BOOK.for_model("claude-opus-5").input == 5.0
    # Longest matching known id wins over a shorter prefix.
    assert BOOK.for_model("claude-opus-5-5-2026").input == 4.0
    assert BOOK.for_model("mystery").input == 5.0


def test_load_reads_shipped_table() -> None:
    book = prices.load()
    assert book.default in book.models
    assert book.for_model("claude-sonnet-5-5").cache_read == 0.2


def test_load_custom_path(tmp_path: Path) -> None:
    path = tmp_path / "p.json"
    path.write_text(
        json.dumps(
            {
                "default": "m",
                "models": {"m": {"input": 1, "output": 2, "cache_read": 3}},
            },
        ),
        encoding="utf-8",
    )
    book = prices.load(path)
    assert book.models["m"] == prices.Price(1.0, 2.0, 3.0)


def test_price_of_without_split_prices_creation_as_5m() -> None:
    usage = {"input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000}
    assert _cost(usage) == pytest.approx(5.0 + 1.25 * 5.0)


def test_price_of_with_split_prices_1h_at_double() -> None:
    usage = {
        "cache_creation_input_tokens": 1_000_000,
        "cache_creation_1h": 400_000,
        "cache_creation_5m": 600_000,
        "cache_read_input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
    }
    expected = 0.4 * 2.0 * 5.0 + 0.6 * 1.25 * 5.0 + 0.5 + 25.0
    assert _cost(usage) == pytest.approx(expected)


def test_price_of_zero_for_empty_usage() -> None:
    assert _cost({}) == 0.0


def test_price_of_defaults_to_shipped_prices() -> None:
    usage = {"output_tokens": 1_000_000}
    assert prices.price_of("claude-sonnet-5-5", usage) == pytest.approx(10.0)
    assert prices.PRICES.default in prices.PRICES.models


def test_t2370_fable_5_2_has_its_own_price_row() -> None:
    """Fable 5.2 fell through to the Opus 5.5 default and was priced at half."""
    row = prices.PRICES.for_model("claude-fable-5-2")
    assert prices.PRICES.models["claude-fable-5-2"] == row
    assert (row.input, row.output, row.cache_read) == (8.0, 40.0, 0.2)
    assert row != prices.PRICES.for_model(prices.PRICES.default)
    # The 5.1 row must not swallow 5.2 ids by prefix, nor the reverse.
    assert prices.PRICES.for_model("claude-fable-5-1").input == 10.0
    assert prices.PRICES.for_model("claude-fable-5-2-20261101").input == 8.0


def test_t2370_fable_5_2_matches_the_measured_probe() -> None:
    """`claude -p 'say ok'` billed total_cost_usd 0.4225 (18 output tokens)."""
    usage = {
        "input_tokens": 2,
        "output_tokens": 18,
        "cache_creation_input_tokens": 26211,
        prices.CACHE_1H: 26211,
        "cache_read_input_tokens": 11826,
    }
    assert prices.price_of("claude-fable-5-2", usage) == pytest.approx(0.4225, abs=1e-4)


FREE_GATEWAY_IDS = (
    "agnes-2.5-flash",
    "gpt-oss-120b",
    "nvidia/nemotron-3-ultra-550b-a55b",
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "mistralai/mistral-large-2512",
    "aisingapore/Qwen-SEA-LION-v4-32B-IT",
    "kilo-auto/free",
)


def test_t2380_haiku_5_5_has_its_own_price_row() -> None:
    """Haiku 5.5 fell through to the Opus 5.5 default and was priced 40x too high."""
    row = prices.PRICES.models["claude-haiku-5-5"]
    # List price for prompts up to 100K tokens; cache reads are 0.1x input.
    assert (row.input, row.output, row.cache_read) == (0.10, 0.50, 0.01)
    assert row != prices.PRICES.for_model(prices.PRICES.default)
    # The 4.5 row must not swallow 5.5 ids by prefix, nor the reverse.
    assert prices.PRICES.for_model("claude-haiku-4-5").input == 1.0
    assert prices.PRICES.for_model("claude-haiku-5-5-20261101").input == 0.10


def test_t2380_mythos_5_2_is_priced_like_fable_5_2() -> None:
    """Mythos 5.2 is the same model as Fable 5.2 with the same per-token price."""
    row = prices.PRICES.models["claude-mythos-5-2"]
    assert row == prices.PRICES.models["claude-fable-5-2"]
    assert (row.input, row.output, row.cache_read) == (8.0, 40.0, 0.2)


@pytest.mark.parametrize("model", FREE_GATEWAY_IDS)
def test_t2380_free_gateway_model_has_its_own_zero_row(model: str) -> None:
    """Gateway models cost kuhy nothing; they were billed as Opus 5.5."""
    assert model in prices.PRICES.models
    assert prices.PRICES.models[model] == prices.Price(0.0, 0.0, 0.0)
    usage = {
        "input_tokens": 1_000,
        "output_tokens": 1_000,
        "cache_creation_input_tokens": 1_000,
        "cache_read_input_tokens": 1_000,
    }
    assert prices.price_of(model, usage) == 0.0
