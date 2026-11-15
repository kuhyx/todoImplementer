"""The live cost meter and the registry of running credit turns."""

from __future__ import annotations

from typing import Any

import pytest
from todoimpl.credits import live
from todoimpl.credits.meter import Meter


def assistant(
    msg: str, *, usage: dict[str, Any] | None = None, content: list[Any] | None = None
) -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {"id": msg, "model": "claude-sonnet-5-5", "usage": usage or {}, "content": content or []},
    }  # these tests pin the Sonnet rates; test_models.py covers the other models


def test_an_empty_meter_costs_nothing_and_ignores_other_events() -> None:
    meter = Meter()
    assert meter.cost() == 0.0
    assert meter.feed({"type": "user", "message": {}}) is False
    assert meter.feed({"type": "assistant", "message": "not a dict"}) is False
    assert meter.cost() == 0.0


def test_usage_is_priced_at_the_sonnet_list_prices() -> None:
    meter = Meter()
    usage = {
        "input_tokens": 1_000_000, "output_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000, "cache_creation_input_tokens": 1_000_000,
    }  # fmt: skip
    assert meter.feed(assistant("m1", usage=usage)) is True
    assert meter.cost() == pytest.approx(3.0 + 15.0 + 0.30 + 3.75)


def test_a_message_split_over_events_counts_once_with_its_largest_usage() -> None:
    meter = Meter()
    meter.feed(assistant("m1", usage={"input_tokens": 100, "output_tokens": 3}))
    meter.feed(assistant("m1", usage={"input_tokens": 100, "output_tokens": 50, "bogus": 1}))
    meter.feed(assistant("m1", usage={"input_tokens": True, "output_tokens": "x"}))
    assert meter.cost() == pytest.approx((100 * 3.0 + 50 * 15.0) / 1e6)
    meter.feed(assistant("m2", usage={"input_tokens": 100}))
    assert meter.cost() == pytest.approx((200 * 3.0 + 50 * 15.0) / 1e6)


def test_output_is_at_least_what_the_blocks_weigh_because_the_usage_count_is_a_first_snapshot() -> None:
    meter = Meter()
    blocks = [
        {"type": "text", "text": "x" * 300},
        {"type": "tool_use", "input": {"command": "y" * 280}},
        {"type": "thinking", "thinking": "z" * 30, "signature": "s" * 60},
        {"type": "image"},
        "junk",
    ]
    meter.feed(assistant("m1", usage={"output_tokens": 3}, content=blocks))
    tokens = 300 / 3 + len('{"command": "' + "y" * 280 + '"}') / 3 + 30 / 3 + 60 / 6
    assert meter.cost() == pytest.approx(tokens * 15.0 / 1e6)
    big = Meter()
    big.feed(assistant("m1", usage={"output_tokens": 10_000}, content=[{"type": "text", "text": "hi"}]))
    assert big.cost() == pytest.approx(10_000 * 15.0 / 1e6)


def test_the_registry_tracks_cards_costs_and_hooks(tmp_path: Any) -> None:
    live.reset()
    live.begin(tmp_path, "aaaaaaaa-0")
    live.begin(tmp_path, "aaaaaaaa-0")
    live.set_cost(tmp_path, "bbbbbbbb-0", 1.5)  # a cost can arrive before the claim
    assert live.running(tmp_path) == 2
    assert sorted(live.costs(tmp_path)) == [0.0, 1.5]
    assert live.stoppers(tmp_path) == []
    live.attach(tmp_path, "aaaaaaaa-0", lambda: None, lambda: None)
    live.attach(tmp_path, "cccccccc-0", lambda: None, lambda: None)  # a hook attach also counts the card
    assert len(live.stoppers(tmp_path)) == 2
    live.end(tmp_path, "aaaaaaaa-0")
    live.end(tmp_path, "aaaaaaaa-0")
    assert live.running(tmp_path) == 2
