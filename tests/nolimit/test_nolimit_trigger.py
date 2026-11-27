"""The no-limit runner works only while the plan is limited, the credits take no turn and free has none."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nolimitfakes import park, public
from runnerfakes import Env
from todoimpl.credits import route
from todoimpl.nolimit import trigger
from todoimpl.usage import hold

NOW = 1_000_000.0


def up() -> bool:
    return True


def down() -> bool:
    return False


def test_t2541_trigger_needs_a_limit_no_credits_and_no_free_card(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = world.root
    assert not trigger.holds(root, NOW, up)  # no run root yet: the plan is not limited
    park(root, "aaaa1111-0", repo="kuhyx/private")
    assert trigger.holds(root, NOW, up)  # limited, credits off, the only waiting card is private
    public(world.home, "kuhyx/open")
    park(root, "bbbb2222-0", repo="kuhyx/open")
    assert not trigger.holds(root, NOW, up)  # a public card could go free
    assert trigger.holds(root, NOW, down)  # ... but the gateway is down
    monkeypatch.setattr(route, "choose", lambda _root, _now: route.Choice(route.CREDITS))
    assert not trigger.holds(root, NOW, down)  # the credits take the turn


def test_error_fix_cards_never_count_as_free(world: Env) -> None:
    public(world.home, "kuhyx/open")
    park(world.root, "cccc3333-0", repo="kuhyx/open", body="Error-Signature: app:x")
    assert trigger.holds(world.root, NOW, up)


def test_the_weekly_hold_and_the_limit_mark_limit_the_plan(world: Env) -> None:
    root = world.root
    root.mkdir(parents=True)
    hold.observe(root, 0.96, NOW + 60, NOW)
    assert trigger.plan_limited(root, NOW)
    assert not trigger.plan_limited(root, NOW + 120)  # the window reset
    (root / "limit-until").write_text(str(NOW + 600), encoding="utf-8")
    assert trigger.plan_limited(root, NOW + 120)


def test_runs_that_are_not_paused_or_unreadable_do_not_count(world: Env, tmp_path: Path) -> None:
    root = world.root
    park(root, "dddd4444-0", stage="implement")
    bad = root / "eeee5555-0"
    bad.mkdir()
    (bad / "state.json").write_text(json.dumps({"stage": 3}), encoding="utf-8")
    (root / "loose-file").write_text("x", encoding="utf-8")
    (root / "no-state").mkdir()
    assert not trigger.plan_limited(root, NOW)
