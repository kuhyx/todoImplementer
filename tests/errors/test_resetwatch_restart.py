"""The reset watch across restarts, cut ticks, a busy card and a todo app that is down."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest
from resetfakes import CARD, T0, WEEK, Watch
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.http.backend import BackendError
from todoimpl.runner import resetwatch, tokenopt

if TYPE_CHECKING:
    from fake_todo_mcp import FakeTodoMcp
    from servicefakes import Rig
    from todoimpl.http.newtask import NewTask


@pytest.fixture
def w(rig: Rig, fake: FakeTodoMcp) -> Watch:
    return Watch(rig, fake)


def test_t2552_a_restart_never_files_a_second_note(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.now = T0 + 60.0
    w.tick()
    w.watch = w.make()
    w.tick()
    w.watch = w.make()
    w.tick()
    assert len(w.added()) == 1
    assert len(w.starts()) == 1


class LateCard:
    """Adds the note, then says its card is not on the board yet (NewTaskService NOT_FOUND)."""

    def __init__(self, real: Any) -> None:
        self.real = real

    def create(self, task: NewTask) -> tuple[str, str | None]:
        self.real.add(task)
        raise BackendError("not_found", "note got the task, but its card is not on the board yet")


def test_t2552_a_note_filed_before_a_cut_tick_is_found_by_its_line(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.creator = LateCard(w.rig.backend.new_task_service)
    w.watch = w.make()
    w.tick()
    assert len(w.added()) == 1
    assert w.starts() == []
    w.rig.backend.cache.refresh()
    w.watch = w.make()  # restart
    w.tick()
    assert len(w.added()) == 1
    assert w.starts() == [("start", CARD, True)]


def test_t2552_a_start_a_cut_tick_did_not_record_is_not_made_twice(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.now = T0 + 60.0
    w.tick()
    key = tokenopt.iso(T0)
    resetwatch.save(w.rig.root, {**w.state(), "pending": {"key": key, "card": CARD}})  # cut before the save
    w.tick()
    assert len(w.starts()) == 1
    assert w.state()["pending"] is None


def test_t2553_a_busy_card_starts_when_its_cycle_ships(w: Watch) -> None:
    save(run_dir(w.rig.root, CARD), RunState(task_id=CARD, stage="implement"))
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.tick()
    w.tick()
    assert len(w.added()) == 1
    assert w.starts() == []
    save(run_dir(w.rig.root, CARD), RunState(task_id=CARD, stage="shipped"))
    w.tick()
    assert len(w.starts()) == 1


def test_t2553_a_refused_start_raises_and_the_next_tick_starts_it(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.sched.refuse = RuntimeError("conflict")
    with pytest.raises(RuntimeError):
        w.tick()
    assert w.state()["pending"]["card"] == CARD
    w.sched.refuse = None
    w.tick()
    assert len(w.starts()) == 1


def test_t2553_the_todo_app_down_retries_and_a_part_closed_by_hand_is_dropped(w: Watch) -> None:
    w.week(T0)
    w.tick()
    w.week(T0 + WEEK)
    w.now = T0 + 60.0
    w.creator = Down()
    w.watch = w.make()
    w.tick()
    assert w.state()["pending"] == {"key": tokenopt.iso(T0)}
    w.creator = Ghost()
    save(run_dir(w.rig.root, "ffff0000-0"), RunState(task_id="ffff0000-0", stage="implement"))
    w.watch = w.make()
    w.tick()  # filed, but the card never shows up: closed by hand after MISSING_TICKS
    assert w.state()["pending"]["card"] == "ffff0000-0"
    w.tick()
    w.tick()
    assert w.state()["pending"] is None
    assert w.starts() == []


class Down:
    def create(self, task: NewTask) -> tuple[str, str | None]:
        raise BackendError("upstream_unavailable", "todo app down")


class Ghost:
    def create(self, task: NewTask) -> tuple[str, str | None]:
        return "ffff0000", "ffff0000-0"
