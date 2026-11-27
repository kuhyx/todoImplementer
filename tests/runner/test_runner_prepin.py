"""A pick before Start only saves the model, and the Start that follows runs every turn on it (T2478)."""

from __future__ import annotations

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait_stage
from todoimpl import modelpick
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import prepin
from todoimpl.runner.scheduler import RunnerError

FABLE, OPUS, SONNET, HAIKU = (m.id for m in modelpick.MODELS)


def test_t2478_a_pick_on_a_card_with_no_run_saves_it_and_starts_nothing(world: Env) -> None:
    sched, _ = boot(world)
    try:
        sched.set_model(CARD, SONNET)
        assert store.load(world.root / CARD) is None  # still Backlog: no run, no queue, no turn
        assert prepin.read(world.root / CARD) == SONNET
        assert prepin.read_card(world.root, CARD) == SONNET
        assert CARD not in sched.running()
        assert world.calls() == []
        sched.set_model(CARD, modelpick.DEFAULT)
        assert prepin.read(world.root / CARD) is None
        assert not (world.root / CARD / prepin.FILE).exists()
    finally:
        sched.close()


def test_t2478_start_runs_every_turn_on_the_saved_pick(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.set_model(CARD, SONNET)
        sched.start(CARD)
        st = wait_stage(world, sched, "gate", turns=3)
        assert [c["model"] for c in world.calls()] == [SONNET, SONNET, SONNET]
        assert st.extra[modelpick.PIN] == SONNET
        assert not (world.root / CARD / prepin.FILE).exists()  # the run holds it now
    finally:
        sched.close()


def test_t2478_with_no_pick_start_runs_on_the_role_model(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate", turns=3)
        assert modelpick.PIN not in st.extra
        assert {c["model"] for c in world.calls()} == {"sonnet"}
    finally:
        sched.close()


def test_t2478_a_pick_on_a_cancelled_card_waits_for_restart(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        store.save(world.root / CARD, RunState(task_id=CARD, stage="cancelled", extra={"last_model": "opus"}))
        sched.set_model(CARD, HAIKU)
        st = state(world)
        assert (st.stage, st.extra[modelpick.PIN]) == ("cancelled", HAIKU)
        assert CARD not in sched.running()
        assert world.calls() == []
        sched.start(CARD)
        wait_stage(world, sched, "gate", turns=3)
        assert {c["model"] for c in world.calls()} == {HAIKU}
    finally:
        sched.close()


def test_t2478_a_pick_on_a_manual_or_missing_note_is_refused(world: Env) -> None:
    sched, _ = boot(world, title="MANUAL WORK REQUIRED: plug the cable")
    try:
        with pytest.raises(RunnerError) as manual:
            sched.set_model(CARD, SONNET)
        assert manual.value.code == "disabled"
        with pytest.raises(RunnerError) as gone:
            sched.set_model("ffff0000-0", SONNET)
        assert gone.value.code == "not_found"
        assert prepin.read(world.root / CARD) is None
    finally:
        sched.close()


def test_t2478_a_broken_pin_file_reads_as_no_pick(world: Env) -> None:
    (world.root / CARD).mkdir(parents=True)
    (world.root / CARD / prepin.FILE).write_text('{"model": "gpt-5"}', encoding="utf-8")
    assert prepin.read(world.root / CARD) is None


def test_t2478_a_closing_cancelled_run_takes_no_pick(world: Env) -> None:
    sched, _ = boot(world)
    try:
        closing = RunState(
            task_id=CARD, stage="cancelled", auto_start={"reason": "done_check", "passed_at": 1.0}
        )
        store.save(world.root / CARD, closing)
        with pytest.raises(RunnerError) as refused:
            sched.set_model(CARD, SONNET)
        assert refused.value.code == "disabled"
        assert modelpick.PIN not in state(world).extra
    finally:
        sched.close()
