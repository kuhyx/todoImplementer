"""The credit cap guard alone: it prices assistant events, says so once, and ignores everything else."""

import json
from datetime import datetime
from pathlib import Path

import pytest
from todoimpl.credits import ledger, live
from todoimpl.runner.creditguard import STOPPED, CreditGuard

NOW = datetime(2026, 11, 8, 12).timestamp()  # noqa: DTZ001 - local time, as the pacing uses


def assistant(msg: str, tokens: int) -> str:
    return json.dumps(
        {"type": "assistant", "message": {"id": msg, "usage": {"output_tokens": tokens}, "content": []}}
    )


@pytest.fixture
def guard(tmp_path: Path) -> CreditGuard:
    ledger.reset()
    live.reset()
    live.begin(tmp_path, "abcd1234-0")
    return CreditGuard(tmp_path, "abcd1234-0", lambda: NOW)


def test_it_keeps_the_live_cost_and_the_result_carries_it(guard: CreditGuard, tmp_path: Path) -> None:
    assert guard.feed(assistant("m1", 1_000_000)) == []  # $20 at the default Opus rates: far under any cap
    assert guard.result.live_usd == pytest.approx(20.0)
    assert live.costs(tmp_path) == [pytest.approx(20.0)]


def test_other_lines_do_not_move_the_cost(guard: CreditGuard, tmp_path: Path) -> None:
    guard.feed(json.dumps({"type": "user", "message": {}}))
    guard.feed('{"type": "assistant", broken')  # names the type but is not JSON
    guard.feed(json.dumps({"type": "assistant", "message": "text"}))
    assert guard.result.live_usd == 0.0
    assert live.costs(tmp_path) == [0.0]


def test_at_the_cap_it_stops_the_turn_and_says_so_once(guard: CreditGuard, tmp_path: Path) -> None:
    stops: list[str] = []
    live.attach(tmp_path, "abcd1234-0", lambda: stops.append("hit"), lambda: stops.append("stop"))
    first = guard.feed(assistant("m1", 100_000_000))  # $1500 against a cap of at most $190
    assert [a.text for a in first] == [STOPPED]
    assert guard.feed(assistant("m2", 100_000_000)) == []
    assert stops == ["hit", "stop", "hit", "stop"]
