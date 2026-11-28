"""T2533: an emergency reserve of the weekly plan window (kuhy, 2026-11-27).

At 90 % of `seven_day` medium and low cards start no new plan turn (high ones go on); at 95 % every plan turn
stops at once and pauses until the window resets. The hold has its own mark (`usage-hold.json`).
"""

from __future__ import annotations

import json
from functools import partial
from typing import TYPE_CHECKING

import pytest
from todoimpl.board.state import RunState
from todoimpl.credits import route
from todoimpl.repotask import files
from todoimpl.runner import chain, guard, limitprobe
from todoimpl.todo_mcp.items import Item
from todoimpl.usage import hold, oauth

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_800_000_000.0
RESET = NOW + 43200  # day 7 of the window: the daily allowance is 100 %


def _event(used: float, resets: float = RESET) -> str:
    windows = {"seven_day": {"utilization": used, "resetsAt": resets, "status": "allowed"}}
    info = {"status": "allowed", "rateLimitType": "seven_day", "unifiedWindows": windows}
    return json.dumps({"type": "rate_limit_event", "rate_limit_info": info})


def _card(root: Path, card: str, priority: str) -> RunState:
    run = root / card
    run.mkdir(parents=True)
    (run / files.PRIORITY).write_text(json.dumps({"priority": priority}))
    return RunState(card, "planning", repo="kuhyx/private-x")


LEVELS = [(0.5, "none"), (0.9, "low_medium"), (0.949, "low_medium"), (0.95, "all")]


@pytest.mark.parametrize(("used", "want"), LEVELS)
def test_t2533_levels(tmp_path: Path, used: float, want: str) -> None:
    assert hold.observe(tmp_path, used, RESET, NOW) == want
    assert hold.level(tmp_path, NOW) == want
    assert hold.level(tmp_path, RESET) == "none"  # the window reset lifts it


def test_t2533_ninety_holds_low_and_medium_plan_turns_not_high(tmp_path: Path) -> None:
    hold.observe(tmp_path, 0.91, RESET, NOW)
    high, low = _card(tmp_path, "aaaa0001-0", "high"), _card(tmp_path, "aaaa0002-0", "low")
    assert chain.choose(tmp_path, NOW, high).route == route.PLAN
    held = chain.choose(tmp_path, NOW, low)
    assert (held.route, held.until) == (None, RESET)
    assert not chain.admits(tmp_path, NOW, "aaaa0002-0")
    assert chain.claim(tmp_path, NOW, "aaaa0001-0", high).route == route.PLAN


def test_t2533_ninety_five_holds_every_card(tmp_path: Path) -> None:
    hold.observe(tmp_path, 0.96, RESET, NOW)
    high = _card(tmp_path, "aaaa0001-0", "high")
    assert chain.choose(tmp_path, NOW, high).route is None
    assert files.priority(tmp_path / "nowhere") == "medium"


def test_t2533_stream_at_ninety_five_stops_every_running_plan_turn(tmp_path: Path) -> None:
    stopped: list[str] = []
    hits: list[float] = []
    guards = [
        guard.OverageGuard(
            tmp_path, card, partial(stopped.append, card), lambda _t: None, hits.append, lambda: NOW
        )
        for card in ("aaaa0001-0", "aaaa0002-0")
    ]
    guards[0].feed(_event(0.91))
    assert stopped == []
    guards[0].feed(_event(0.96))
    assert sorted(stopped) == ["aaaa0001-0", "aaaa0002-0"]
    assert hits == [RESET, RESET]
    assert hold.level(tmp_path, NOW) == "all"
    guards[1].feed(_event(0.97))  # tripped once: no second stop
    assert len(stopped) == 2


def test_t2533_probe_at_ninety_five_stops_running_turns(tmp_path: Path) -> None:
    stopped: list[str] = []
    keep = guard.OverageGuard(
        tmp_path, "aaaa0003-0", lambda: stopped.append("x"), lambda _t: None, lambda _u: None
    )
    assert hold.apply_probe(tmp_path, 0.95, RESET, NOW) == "all"
    assert stopped == ["x"]
    assert keep.until == RESET


def _probe(share: float) -> oauth.Probe:
    return oauth.Probe(NOW, None, oauth.Window(share, RESET))


def test_t2533_limit_probe_tick_writes_the_hold(tmp_path: Path) -> None:
    probe = limitprobe.LimitProbe(tmp_path, fetch=lambda _n: _probe(0.96), clock=lambda: NOW)
    probe.tick()
    assert hold.level(tmp_path, NOW) == "all"


def test_t2533_limit_probe_waits_a_minute_from_eighty_five(tmp_path: Path) -> None:
    probe = limitprobe.LimitProbe(tmp_path, fetch=lambda _n: _probe(0.86), clock=lambda: NOW)
    assert probe.wait_after(_probe(0.84)) == limitprobe.INTERVAL
    assert probe.wait_after(None) == limitprobe.INTERVAL
    assert probe.wait_after(_probe(0.86)) == limitprobe.NEAR_INTERVAL == 60.0


def test_t2533_a_single_note_card_keeps_its_note_priority(tmp_path: Path) -> None:
    item = Item("aaaa0009", 0, "t", "b", "kuhyx/x", "todo", None)
    files.snapshot(tmp_path, item, "high")
    assert files.priority(tmp_path) == "high"
    assert not (tmp_path / files.PARTS).exists()  # a section card has no parts to tick


def test_t2533_a_halted_turn_is_not_halted_twice(tmp_path: Path) -> None:
    stopped: list[str] = []
    one = guard.OverageGuard(
        tmp_path, "aaaa0004-0", lambda: stopped.append("x"), lambda _t: None, lambda _u: None
    )
    one.halt(RESET, "first")
    one.halt(RESET + 1, "second")
    assert (stopped, one.until) == (["x"], RESET)
