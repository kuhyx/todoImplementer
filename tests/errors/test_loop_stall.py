"""A stall ticket (a running card idle over 60 s) starts first and skips the usage gate (T2403)."""

from __future__ import annotations

from errfakes import kartka_entry
from loopfakes import CARD, World
from todoimpl.errors.sources import Source, state_base
from todoimpl.repotask.ids import repo_card_id
from todoimpl.stall import report, slowstep


def _with_stall(world: World) -> str:
    report.file("stall-memory", "card 587cf325-0 idle 2820 s: board slice memory pressure 94 %", 1000.0)
    stall = Source(report.APP, "", "contract", report.path())
    world.loop.sources = lambda: [world.source, stall]
    return repo_card_id(report.REPO)


def test_t2403_a_stall_ticket_starts_even_when_usage_is_high(world: World) -> None:
    board = _with_stall(world)
    world.reason = None  # weekly use over 80 %, no credits, no free models
    world.tick()
    assert world.starts() == [("start", board, True)]
    extra = world.sched.extras[0]
    assert extra is not None
    assert extra["app_error"]["reason"] == "stall"
    assert extra["app_error"]["keys"] == [f"{report.APP}:stall-memory"]


def test_t2403_a_stall_ticket_starts_before_any_other_error_card(world: World) -> None:
    world.entries(kartka_entry())
    board = _with_stall(world)
    world.tick()
    world.tick()
    assert [start[1] for start in world.starts()] == [board, CARD]


def test_t2437_a_routed_slow_step_starts_even_when_usage_is_high(world: World) -> None:
    """A routed slow-step stall is ungated and starts first, same as a board stall."""
    kartka = repo_card_id("kuhyx/kartka")
    slowstep.file("kuhyx/kartka", "gate-test-s3", "card x quiet 70 s: gate step over 60 s", 1000.0)
    stall = Source("kartka", "", "contract", state_base() / "app-errors" / slowstep.FILE)
    world.loop.sources = lambda: [world.source, stall]
    world.reason = None  # weekly use over 80 %, no credits, no free models
    world.tick()
    assert world.starts() == [("start", kartka, True)]
    extra = world.sched.extras[0]
    assert extra is not None
    assert extra["app_error"]["reason"] == "stall"
    assert extra["app_error"]["keys"] == ["kartka:slow-gate-test-s3"]
