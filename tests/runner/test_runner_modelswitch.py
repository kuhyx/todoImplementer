"""kuhy pins a card to a model: its stage runs again on it, a live turn is cut and resumed (T2216, T2217)."""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING, cast

import pytest
from adoptfakes import env, go, rig
from contract_lib import validate
from creditfakes import enable_credits
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait, wait_stage
from todoimpl import modelpick
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import limits, modelswitch
from todoimpl.runner.files import write_json
from todoimpl.runner.scheduler import RunnerError, Scheduler
from todoimpl.runner.turn import run_turn

if TYPE_CHECKING:
    from pathlib import Path

FABLE, OPUS, SONNET, HAIKU = (m.id for m in modelpick.MODELS)
CUT = ({"_fake": "sleep", "sec": 30},)  # an implement turn that is still running when kuhy picks


def test_t2216_a_resting_card_runs_its_stage_again_on_the_picked_model_in_the_same_session(
    world: Env,
) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        before = wait_stage(world, sched, "gate", turns=3)
        sid = before.sessions["implement"]["session_id"]
        sched.set_model(CARD, FABLE)
        st = wait_stage(world, sched, "gate", turns=3)
        again = world.calls()[3:]
        assert [c["model"] for c in again] == [FABLE, FABLE]  # implement, then live check: every role
        assert again[0]["resume"] == sid  # claude 2.1.328 switches the model of a resumed session
        assert "again on claude-fable-5-2" in str(again[0]["prompt"])
        assert st.extra[modelpick.PIN] == FABLE
        assert st.extra["last_model"] == FABLE
        validate("state", st.to_dict())
    finally:
        sched.close()


def test_t2216_a_live_turn_is_cut_and_resumed_on_the_picked_model(world: Env) -> None:
    sched, _ = boot(world, PLAN, CUT, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: len(world.calls()) == 2 and CARD in sched.running())
        run = world.root / CARD
        wait(
            lambda: any('"init"' in p.read_text() for p in run.glob("implement-*.stream.jsonl"))
        )  # its session
        sched.set_model(CARD, SONNET)
        assert modelpick.PIN not in state(world).extra  # the live drive owns state.json until it ends
        st = wait_stage(world, sched, "gate", turns=3)
        cut, resumed, live = world.calls()[1:]
        assert (resumed["model"], live["model"]) == (SONNET, SONNET)
        assert resumed["resume"] is not None
        assert resumed["resume"] == st.sessions["implement"]["session_id"]
        assert "mid-turn" in str(resumed["prompt"])
        assert cut["model"] == "opus"
        assert st.extra[modelpick.PIN] == SONNET
        assert not (world.root / CARD / modelswitch.FILE).exists()
    finally:
        sched.close()


def test_t2216_cancel_after_a_live_pick_keeps_the_card_cancelled(world: Env) -> None:
    sched, _ = boot(world, PLAN, CUT, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: len(world.calls()) == 2 and CARD in sched.running())
        sched.set_model(CARD, SONNET)
        sched.cancel(CARD)
        st = wait_stage(world, sched, "cancelled")
        assert modelpick.PIN not in st.extra
        assert len(world.calls()) == 2  # no turn on the pick
    finally:
        sched.close()


def test_t2216_default_drops_the_pin_and_a_paused_card_only_keeps_it(world: Env) -> None:
    sched, _ = boot(world)
    try:
        with pytest.raises(RunnerError) as missing:
            sched.set_model(CARD, FABLE)
        assert missing.value.code == "not_found"
        run = world.root / CARD
        store.save(run, RunState(task_id=CARD, stage="paused_limit", extra={modelpick.PIN: FABLE}))
        sched.set_model(CARD, modelpick.DEFAULT)
        st = state(world)
        assert (st.stage, modelpick.PIN in st.extra) == ("paused_limit", False)
        assert CARD not in sched.running()
        with pytest.raises(RunnerError) as unknown:
            sched.set_model(CARD, "gpt-5")
        assert unknown.value.code == "bad_request"
        store.save(run, RunState(task_id=CARD, stage="shipped"))
        with pytest.raises(RunnerError) as over:
            sched.set_model(CARD, FABLE)
        assert over.value.code == "disabled"
    finally:
        sched.close()


def test_t2216_a_pick_a_restart_cut_is_settled_when_the_server_starts(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, done_check="true")
    sched.start(CARD)
    st = wait_stage(world, sched, "gate", turns=3)
    sched.close()
    st.stage = "cancelled"  # the cut drive saved this, then the server went down before `after_drive`
    store.save(world.root / CARD, st)
    write_json(world.root / CARD / modelswitch.FILE, {"model": HAIKU, "stage": "implement"})
    again = Scheduler(client, world.root, check_timeout=20)
    try:
        st = wait_stage(world, again, "gate", turns=3)
        assert [c["model"] for c in world.calls()[3:]] == [HAIKU, HAIKU]
        assert st.extra[modelpick.PIN] == HAIKU
    finally:
        again.close()


def test_t2217_the_pin_beats_the_model_the_tier_asks_for(world: Env, tmp_path: Path) -> None:
    run_dir, wt = rig(world, tmp_path)
    world.script("abcd1234", {"_fake": "result", "text": "D: ok"})
    pinned = RunState(task_id="abcd1234-0", stage="implement", extra={modelpick.PIN: FABLE})
    run_turn(env(run_dir, wt, []), pinned, "implement", go, model="sonnet")  # the research tier's Sonnet
    assert world.calls()[-1]["model"] == FABLE


def test_t2217_a_credit_turn_runs_the_pin_not_credits_model(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate", turns=3)
        enable_credits(monkeypatch)
        limits.write_until(world.root, time.time() + 3600)  # the plan is limited: credits take the turns
        sched.set_model(CARD, HAIKU)
        st = wait_stage(world, sched, "gate", turns=3)
        again = world.calls()[3:]
        assert all(c["via_sdk"] and c["model"] == HAIKU for c in again)
        assert "credit_downgrade" not in st.extra  # the role asked for nothing: kuhy did
    finally:
        sched.close()


class _Live:
    """A Scheduler whose one card has a live drive: recover only stops it."""

    def __init__(self, root: Path) -> None:
        self.root, self._cv, self._active = root, threading.Condition(), {CARD}
        self.killed: list[str] = []

    def kill(self, card: str) -> None:
        self.killed.append(card)


def test_t2216_settle_keeps_a_card_that_shipped_meanwhile_and_skips_a_missing_run(world: Env) -> None:
    sched, _ = boot(world)
    try:
        (world.root / "zzzz0000-0").mkdir(parents=True)
        write_json(world.root / "zzzz0000-0" / modelswitch.FILE, {"model": FABLE, "stage": "implement"})
        assert not modelswitch.settle(sched, "zzzz0000-0")
        store.save(world.root / CARD, RunState(task_id=CARD, stage="shipped"))
        write_json(world.root / CARD / modelswitch.FILE, {"model": FABLE, "stage": "implement"})
        assert modelswitch.settle(sched, CARD)
        st = state(world)
        assert (st.stage, st.extra[modelpick.PIN]) == ("shipped", FABLE)
        assert CARD not in sched.running()
    finally:
        sched.close()
    write_json(world.root / CARD / modelswitch.FILE, {"model": FABLE, "stage": "implement"})
    live = _Live(world.root)
    modelswitch.recover(cast("Scheduler", live))
    assert live.killed == [CARD]  # its `after_drive` settles the pick


def test_t2218_the_overlay_shows_the_pending_pin_but_never_reopens_a_shipped_run(tmp_path: Path) -> None:
    write_json(tmp_path / modelswitch.FILE, {"model": FABLE, "stage": "implement"})
    shipped = modelswitch.overlay(tmp_path, RunState(task_id=CARD, stage="shipped"))
    assert (shipped.stage, shipped.extra[modelpick.PIN]) == ("shipped", FABLE)
    cut = RunState(task_id=CARD, stage="cancelled", extra={modelpick.PIN: OPUS})
    shown = modelswitch.overlay(tmp_path, cut)
    assert (shown.stage, shown.extra[modelpick.PIN], cut.extra[modelpick.PIN]) == ("implement", FABLE, OPUS)
