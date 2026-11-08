"""An attached phone turn that still ends `A: phone:` is not requeued while the Pixel stays in."""

from pathlib import Path

from phonefakes import READY, SERIAL, adb_calls, fake_adb
from runnerfakes import Env
from schedfakes import CARD, boot, state
from todoimpl.board import state as store
from todoimpl.board.needs import needs
from todoimpl.board.state import RunState
from todoimpl.runner import phone
from todoimpl.runner.phone_sched import PhoneWatcher
from todoimpl.runner.stream import TurnResult


def attached_turn_ended(text: str = "A: phone: merge and deploy first, then I run C7") -> RunState:
    """Return a run whose phone-attached turn just ended on `text`, after `after_turn`."""
    st = RunState(task_id=CARD, stage="live_check", extra={"waiting_phone": READY, "phone_attached": True})
    res = TurnResult(text=text, tag="A")
    phone.after_turn(st, Path("/nonexistent-run-dir"), res)
    return st


def test_t1818_an_attached_turn_that_asks_again_is_not_requeued_while_plugged(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world)
    try:
        store.save(world.root / CARD, attached_turn_ended())
        assert sched.phone_waiting() == []
        assert PhoneWatcher(sched).tick() is False
        assert state(world).last_tag == "A"
        assert world.calls() == []
    finally:
        sched.close()


def test_t1819_unplugging_and_replugging_runs_the_phone_turn_once_more(world: Env) -> None:
    adb = fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world)
    try:
        store.save(world.root / CARD, attached_turn_ended())
        watcher = PhoneWatcher(sched)
        assert watcher.tick() is False
        (adb / "devices").write_text("", encoding="utf-8")
        assert watcher.tick() is False
        assert len(adb_calls(adb)) == 2  # adb still polled for a card that only waits on a replug
        assert sched.phone_waiting() == [CARD]
        (adb / "devices").write_text(f"{SERIAL} device\n", encoding="utf-8")
        assert watcher.tick() is True
    finally:
        sched.close()


def test_t1820_the_board_shows_the_real_ask_not_plug_in_the_pixel() -> None:
    got = needs(attached_turn_ended())
    assert got.kind == "claude_action"
    assert got.text == "merge and deploy first, then I run C7"
    assert "Plug in" not in got.text


def test_a_fresh_staged_check_with_the_phone_plugged_in_still_runs_once(tmp_path: Path) -> None:
    st = RunState(
        task_id=CARD, stage="live_check", extra={"waiting_phone": {**READY, "tried_attached": True}}
    )
    (tmp_path / "phone_ready.json").write_text('{"apk": "/new.apk"}', encoding="utf-8")
    phone.after_turn(st, tmp_path, TurnResult(text="A: phone: new build staged", tag="A"))
    assert st.extra["waiting_phone"] == {"apk": "/new.apk", "note": "new build staged"}


def test_unplug_skips_a_card_that_no_longer_waits_on_a_replug(world: Env) -> None:
    sched, _ = boot(world)
    try:
        store.save(world.root / CARD, RunState(task_id=CARD, stage="live_check", last_tag="D"))
        sched.phone_unplugged([CARD, "nope0000-0"])
        assert state(world).extra == {}
    finally:
        sched.close()
