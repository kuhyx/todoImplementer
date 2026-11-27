"""The reset watch: one token optimization note per usage reset, started first, never filed twice."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from resetfakes import CARD, T0, WEEK, Watch
from todoimpl.runner import limits, tokenopt

if TYPE_CHECKING:
    from fake_todo_mcp import FakeTodoMcp
    from servicefakes import Rig


@pytest.fixture
def w(rig: Rig, fake: FakeTodoMcp) -> Watch:
    return Watch(rig, fake)


def test_t2558_a_weekly_reset_files_one_high_note_and_starts_it_first(w: Watch) -> None:
    w.week(T0)
    w.tick()  # a first start only learns the window
    assert w.added() == []
    assert w.state()["week_resets_at"] == T0
    w.now = T0 + 120.0
    w.week(T0 + WEEK)
    w.tick()
    (added,) = w.added()
    key = tokenopt.iso(T0)
    assert (added["repo"], added["priority"]) == (tokenopt.REPO, "high")
    assert added["title"] == f"Token optimization after reset {key[:10]}"
    for step in tokenopt.STEPS:
        assert step in added["body"]
    assert "\ndone: " in added["body"]  # spares the Spec stage: no questions
    assert f"Reset-Key: {key}" in added["body"]
    assert w.starts() == [("start", CARD, True)]
    assert w.sched.extras[0] == {"tokenopt": {"key": key, "at": T0 + 120.0}}
    ((card, line),) = w.lines  # the feed line; the test home has no ~/.claude to make a worktree of
    assert card == CARD
    assert line.startswith(f"token optimization after reset {key[:10]}; no ~/.claude worktree: ")
    assert w.state()["last_reset"] == key
    assert w.state()["pending"] is None
    for _ in range(3):
        w.tick()
    assert len(w.added()) == 1


def test_t2558_jitter_in_resets_at_is_no_reset(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + 0.4)
    w.tick()
    w.week(T0 - 2.0)
    w.tick()
    assert w.added() == []
    assert w.state().get("pending") is None


def test_t2551_weekly_reset_and_limit_lift_together_make_one_note(w: Watch) -> None:
    w.week(T0)
    w.paused(T0)
    w.tick()
    assert w.state()["limit_seen"] == T0
    w.now = T0 + 60.0
    limits.clear(w.rig.root)
    w.week(T0 + WEEK)
    w.tick()
    assert len(w.added()) == 1
    assert w.state()["limit_seen"] is None


def test_t2551_a_lift_and_a_late_weekly_probe_are_still_one_reset(w: Watch) -> None:
    w.week(T0)
    w.paused(T0)
    w.tick()
    w.now = T0 + 5.0
    w.tick()  # limit-until ran out by time: the lift, keyed by the reset instant
    assert len(w.added()) == 1
    w.now = T0 + 300.0
    w.week(T0 + WEEK)  # the probe sees the new week five minutes later
    w.tick()
    assert len(w.added()) == 1


def test_t2551_a_lift_alone_files_a_note_and_a_held_limit_without_a_paused_card_does_not(w: Watch) -> None:
    limits.write_until(w.rig.root, T0)
    w.tick()
    assert w.state()["limit_seen"] is None  # nothing rested paused_limit
    w.paused(T0)
    w.tick()
    w.now = T0 + 10.0
    w.tick()
    (added,) = w.added()
    assert f"Reset-Key: {tokenopt.iso(T0)}" in added["body"]
