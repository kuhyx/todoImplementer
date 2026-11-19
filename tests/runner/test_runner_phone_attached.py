"""A phone wait never outlives the Pixel: attached means resume, in any stage, with no click (T2080-T2084)."""

import json

from phonefakes import READY, SERIAL, fake_adb, phone_turn
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board import state as store
from todoimpl.board.needs import needs
from todoimpl.board.state import RunState
from todoimpl.runner import phone_sched
from todoimpl.runner.phone_sched import PhoneWatcher

ATTACHED = "The Pixel is attached now"


def stale_spec_wait() -> RunState:
    """Return the state ab42e0a7-0 was stuck in: the spec stage with the phone wait of an old live check."""
    return RunState(
        task_id=CARD, stage="spec_wait", last_tag="A", repo="kuhyx/demo", extra={"waiting_phone": READY}
    )


def test_t2080_a_spec_turn_never_parks_on_a_stale_phone_stage(world: Env) -> None:
    fake_adb(world)
    sched, _ = boot(world, reply("D:"))
    try:
        store.save(world.root / CARD, stale_spec_wait())
        (world.root / CARD / "phone_ready.json").write_text(json.dumps(READY), encoding="utf-8")
        sched.send(CARD, "it's connected")
        wait(lambda: len(world.calls()) == 1)
        st = wait_stage(world, sched, "spec_wait")
        assert st.last_tag != "A"
        assert "waiting_phone" not in st.extra
    finally:
        sched.close()


def test_t2081_a_phone_wait_on_a_spec_card_is_not_a_phone_ask() -> None:
    assert needs(stale_spec_wait()).kind != "phone"


def test_t2081_a_restart_drops_the_stale_phone_wait_of_a_spec_card(world: Env) -> None:
    sched, _ = boot(world)
    try:
        store.save(world.root / CARD, stale_spec_wait())
        sched.after_recover()
        st = state(world)
        assert "waiting_phone" not in st.extra
        assert st.last_tag is None
        assert needs(st).kind == "spec_ok"
    finally:
        sched.close()


def test_t2082_the_watcher_polls_fast_and_sees_the_pixel_among_emulators(world: Env) -> None:
    assert phone_sched.WATCH_SECS <= 5.0
    fake_adb(world, "emulator-5554 device", "emulator-5556 device", f"{SERIAL} device")
    sched, _ = boot(world, LIVE_OK, done_check="true")
    try:
        store.save(
            world.root / CARD,
            RunState(task_id=CARD, stage="live_check", last_tag="A", extra={"waiting_phone": READY}),
        )
        assert PhoneWatcher(sched).tick() is True
        wait_stage(world, sched, "gate")
        assert ATTACHED in world.calls()[-1]["prompt"]
    finally:
        sched.close()


def test_t2083_a_phone_ask_with_the_pixel_attached_goes_back_to_the_session(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world, PLAN, phone_turn(world), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert ATTACHED in world.calls()[-1]["prompt"]
        assert len(world.calls()) == 3
        assert "waiting_phone" not in st.extra
    finally:
        sched.close()


def test_t2083_the_second_ask_with_the_pixel_attached_rests_instead_of_looping(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    lost = phone_turn(world, tag="A: phone: the phone dropped")
    sched, _ = boot(world, PLAN, phone_turn(world), lost, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "live_check", tag="A")
        assert st.extra["waiting_phone"]["tried_attached"] is True
        assert len(world.calls()) == 3
        assert needs(st).kind == "claude_action"
    finally:
        sched.close()


def test_t2084_send_it_is_connected_resumes_the_phone_check_on_the_pixel(world: Env) -> None:
    adb = fake_adb(world)
    sched, _ = boot(world, PLAN, IMPL, phone_turn(world), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        (adb / "devices").write_text(f"{SERIAL} device\n", encoding="utf-8")
        sched.send(CARD, "it's connected")
        st = wait_stage(world, sched, "gate")
        assert ATTACHED in world.calls()[-1]["prompt"]
        assert "partial" not in st.extra
    finally:
        sched.close()
