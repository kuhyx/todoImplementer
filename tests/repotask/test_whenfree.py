"""Moved work starts on an event: a handoff onto a held repo card starts its next cycle once Ship is done."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest
from repofakes import IMPL, PLAN, Rig, live_for
from test_flow import NUDGED, seed, tick_before_start
from todoimpl.board import state as store
from todoimpl.runner import whenfree
from todoimpl.runner.scheduler import RunnerError, Scheduler
from todoimpl.service import ItemView

if TYPE_CHECKING:
    from pathlib import Path


def cycle_of(rig: Rig, card: str, cycle: int, timeout: float = 30.0) -> store.RunState:
    """Block until the card's run is in `cycle` and no longer shipped (the next cycle began)."""
    end = time.time() + timeout
    while time.time() < end:
        st = store.load(rig.run_dir(card))
        if st is not None and st.extra.get("cycle", 1) == cycle and st.stage != "shipped":
            return st
        time.sleep(0.05)
    pytest.fail(f"{card} never began cycle {cycle}")


def at_gate(rig: Rig) -> tuple[str, str]:
    """Bring a repo card to the gate with one ticked part and two open ones; return (card, note A)."""
    _, card, first, _ = seed(rig)
    rig.script(card, PLAN, IMPL, *NUDGED, live_for(f"{first}-0"))
    tick_before_start(rig, card, f"{first}-0")
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    return card, first


def test_a_handoff_onto_a_card_at_the_gate_starts_the_next_cycle_when_ship_completes(rig: Rig) -> None:
    card, _ = at_gate(rig)
    assert rig.sched.start_when_free(card) is True
    assert whenfree.armed(rig.run_dir(card))
    rig.script(card, PLAN)
    rig.sched.ship(card)
    assert cycle_of(rig, card, 2).auto_ship is False  # the Start a click would make: Ship stays kuhy's
    assert not whenfree.armed(rig.run_dir(card))  # consumed: one handoff, one start


def test_a_card_with_no_pending_handoff_still_waits_for_start_after_ship(rig: Rig) -> None:
    card, _ = at_gate(rig)
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    time.sleep(0.3)
    assert rig.state(card).stage == "shipped"  # "never starts by itself" (DOCS-repotask.md, Cycles)
    assert card not in rig.sched.running()


def test_a_free_card_is_not_armed(rig: Rig) -> None:
    card, _ = at_gate(rig)
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    assert rig.sched.start_when_free(card) is False  # Backlog: the caller presses Start itself
    assert rig.sched.start_when_free("feedf00d-0") is False  # no run at all: Start takes it too
    assert not whenfree.armed(rig.run_dir(card))


def test_the_flag_survives_a_restart_between_ship_and_start(
    rig: Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    card, _ = at_gate(rig)
    rig.sched.start_when_free(card)
    monkeypatch.setattr(whenfree, "spawn", lambda *_: None)  # the server dies before it starts
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    assert whenfree.armed(rig.run_dir(card))
    rig.sched.close()
    monkeypatch.undo()
    rig.script(card, PLAN)
    rig.sched = Scheduler(ItemView(rig.client, rig.cache, rig.world.root), rig.world.root, check_timeout=20)
    assert cycle_of(rig, card, 2).extra["cycle"] == 2


def test_a_click_that_begins_the_next_cycle_drops_the_flag(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    card, _ = at_gate(rig)
    rig.sched.start_when_free(card)
    monkeypatch.setattr(whenfree, "spawn", lambda *_: None)
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    rig.script(card, PLAN)
    rig.sched.start(card)  # kuhy was faster than the event
    assert not whenfree.armed(rig.run_dir(card))


class Starter:
    """A Scheduler stand-in for `release`: its Start raises `error` (or records the card)."""

    def __init__(self, root: Path, error: RunnerError | None) -> None:
        self.root, self.error = root, error
        self.started: list[str] = []

    def start(self, card: str) -> None:
        if self.error is not None:
            raise self.error
        self.started.append(card)


@pytest.mark.parametrize(
    ("error", "kept"),
    [
        (
            RunnerError("no live note with id 475dc1d1", "not_found"),
            False,
        ),  # every part shipped: nothing to do
        (RunnerError("demo-0 is already running", "conflict"), False),  # kuhy started it meanwhile
        (RunnerError("todo MCP: connection refused", "not_found"), True),  # the todo app is away: retry later
    ],
    ids=["gone", "raced", "transient"],
)
def test_a_refused_release_keeps_the_flag_only_for_a_transient_failure(
    tmp_path: Path, error: RunnerError, kept: bool
) -> None:
    (tmp_path / "abcd1234-0").mkdir()
    whenfree.write(tmp_path / "abcd1234-0", 1.0)
    whenfree.release(Starter(tmp_path, error), "abcd1234-0")  # type: ignore[arg-type]
    assert whenfree.armed(tmp_path / "abcd1234-0") is kept


def test_recovery_skips_flags_whose_run_is_unreadable_or_not_shipped(tmp_path: Path) -> None:
    for card, state in (("aaaa0000-0", "{not json"), ("bbbb0000-0", None)):
        (tmp_path / card).mkdir()
        whenfree.write(tmp_path / card, 1.0)
        if state is not None:
            (tmp_path / card / "state.json").write_text(state, encoding="utf-8")
    sched = Starter(tmp_path, None)
    whenfree.recover(sched)  # type: ignore[arg-type]
    assert sched.started == []
