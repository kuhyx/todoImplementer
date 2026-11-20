"""T2360: a card whose note closed has no open asks; a new cycle drops the old reply's."""
# ruff: noqa: PT018

from typing import Any

import pytest
from asksfakes import BODY, ID, PartBody, Rig, Task
from todoimpl.asks import view
from todoimpl.board.state import RunState, load, save
from todoimpl.http.backend import BackendError
from todoimpl.repotask.cycle import new_cycle

REPLY = f"Waiting on you.\n\n{BODY}\nA: answer the asks above."


def _run(rig: Rig, stage: str) -> RunState:
    run = RunState(task_id=ID, stage=stage, extra={"last_reply": REPLY})
    rig.dir.mkdir(parents=True, exist_ok=True)
    save(rig.dir, run)
    return run


@pytest.mark.parametrize("stage", ["shipped", "closed", "done_manually"])
def test_t2360_a_closed_card_offers_and_takes_no_answer(rig: Rig, stage: str) -> None:
    rig.cache.tasks[:] = [Task(ID, "")]
    run = _run(rig, stage)
    assert view.items("", run, rig.dir) == []
    with pytest.raises(BackendError, match="no asks"):
        rig.svc.answer(ID, "c1", "red")
    with pytest.raises(BackendError, match="no asks"):
        rig.svc.take_recommended(ID)
    assert rig.svc.adopt_due() == 0  # stamps when each ask was first seen
    rig.clock.now += view.DAY + 1
    assert rig.svc.adopt_due() == 0
    assert rig.sched.sent == []


def test_t2360_a_closed_single_note_card_hides_its_body_asks_too(rig: Rig) -> None:
    run = _run(rig, "shipped")
    assert view.items(BODY, run, rig.dir) == []


def test_t2360_a_shipped_repo_card_keeps_the_asks_of_its_open_parts(rig: Rig) -> None:
    part: tuple[Any, ...] = (PartBody(BODY.replace("c1", "p1")),)
    run = _run(rig, "shipped")
    got = [i["id"] for i in view.items("", run, rig.dir, part)]
    assert "p1" in got and "c1" not in got


def test_t2360_a_running_card_still_asks_from_its_reply(rig: Rig) -> None:
    run = _run(rig, "implement")
    assert [i["id"] for i in view.items("", run, rig.dir)] == ["c1", "c2", "k1", "s1"]


def test_t2360_a_new_cycle_drops_the_last_cycles_reply(rig: Rig) -> None:
    run = _run(rig, "shipped")
    new_cycle(run, rig.dir)
    run.stage = "spec"
    save(rig.dir, run)
    again = load(rig.dir)
    assert again is not None
    assert "last_reply" not in again.extra
    assert view.items("", again, rig.dir) == []
