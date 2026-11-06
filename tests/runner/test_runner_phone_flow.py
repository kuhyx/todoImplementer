import json
import time

from phonefakes import READY, SERIAL, adb_calls, fake_adb, phone_turn
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.board.status import compute, needs
from todoimpl.runner.phone_sched import PhoneWatcher
from todoimpl.runner.scheduler import Scheduler


def waiting_run(world: Env, card: str, **extra: object) -> RunState:
    """Save a run resting on a phone wait, as a drive that ended `A: phone:` leaves it."""
    st = RunState(task_id=card, stage="implement", last_tag="A", extra={"waiting_phone": READY, **extra})
    store.save(world.root / card, st)
    return st


def test_t1530_a_staged_phone_check_rests_the_run_in_the_phone_category(world: Env) -> None:
    adb = fake_adb(world)
    sched, client = boot(world, PLAN, phone_turn(world), done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        assert st.extra["waiting_phone"] == {**READY, "note": "plug in the Pixel"}
        assert needs(st).kind == "phone"
        assert compute(client.get_task(CARD), st, live=False, limit_until=None).value == "needs_you"
        assert adb_calls(adb) == []
    finally:
        sched.close()


def test_t1531_plugging_in_the_pixel_runs_the_staged_deploy_and_the_live_check(world: Env) -> None:
    adb = fake_adb(world)
    sched, _ = boot(world, PLAN, phone_turn(world), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement", tag="A")
        watcher = PhoneWatcher(sched)
        assert watcher.tick() is False
        assert state(world).stage == "implement"
        (adb / "devices").write_text(f"{SERIAL} device\n", encoding="utf-8")
        assert watcher.tick() is True
        st = wait_stage(world, sched, "gate")
        prompt = world.calls()[-1]["prompt"]
        assert "The Pixel is attached now" in prompt
        assert READY["deploy_cmd"] in prompt
        assert "Verify only C1" in prompt
        assert "waiting_phone" not in st.extra
        assert "phone_attached" not in st.extra
        assert (world.root / CARD / "phone_ready.used.json").exists()
        assert not (world.root / CARD / "phone_ready.json").exists()
    finally:
        sched.close()


def test_t1532_the_emulator_report_is_kept_for_the_phone_turn(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    report = "- [x] C1: ran it on the emulator -> saw hi\n- [~] C2: needs phone: camera\n"
    live = (
        {"_fake": "write", "path": str(world.root / CARD / "live_check.md"), "text": report},
        *phone_turn(world),
    )
    sched, _ = boot(world, PLAN, IMPL, live, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        assert PhoneWatcher(sched).tick() is True
        wait_stage(world, sched, "gate")
        assert (world.root / CARD / "live_check.emulator.md").read_text(encoding="utf-8") == report
    finally:
        sched.close()


def test_t1533_a_waiting_card_survives_a_restart_and_is_not_rerun(world: Env) -> None:
    fake_adb(world)
    sched, _ = boot(world, PLAN, phone_turn(world), done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement", tag="A")
    finally:
        sched.close()
    calls = len(world.calls())
    sched2 = Scheduler(sched.client, world.root, check_timeout=20)
    try:
        time.sleep(0.3)
        assert len(world.calls()) == calls
        assert sched2.phone_waiting() == [CARD]
        saved = json.loads((world.root / CARD / "state.json").read_text(encoding="utf-8"))
        assert saved["waiting_phone"]["pkg"] == "com.kuhy.demo"
    finally:
        sched2.close()


def test_t1534_adb_is_not_forked_while_no_run_waits(world: Env) -> None:
    adb = fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world)
    try:
        store.save(world.root / "idle0000-0", RunState(task_id="idle0000-0", stage="gate", last_tag="D"))
        (world.root / "broken-0").mkdir()
        (world.root / "broken-0" / "state.json").write_text("{", encoding="utf-8")
        assert PhoneWatcher(sched).tick() is False
        assert adb_calls(adb) == []
    finally:
        sched.close()


def test_t1535_one_card_uses_the_phone_at_a_time_oldest_first(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world)
    try:
        waiting_run(world, "aaaa0001-0")
        waiting_run(world, "aaaa0002-0")
        assert sched.phone_waiting() == ["aaaa0001-0", "aaaa0002-0"]
        busy = RunState(task_id="aaaa0003-0", stage="live_check", extra={"phone_attached": True})
        store.save(world.root / "aaaa0003-0", busy)
        with sched._cv:
            sched._queue.append("aaaa0003-0")
        assert sched.phone_waiting() == []
    finally:
        sched.close()


def test_t1536_only_a_resting_phone_wait_can_be_attached(world: Env) -> None:
    sched, _ = boot(world)
    try:
        waiting_run(world, "bbbb0001-0")
        store.save(
            world.root / "bbbb0002-0",
            RunState(task_id="bbbb0002-0", stage="cancelled", last_tag="A", extra={"waiting_phone": READY}),
        )
        store.save(
            world.root / "bbbb0003-0",
            RunState(task_id="bbbb0003-0", stage="implement", last_tag="D", extra={"waiting_phone": READY}),
        )
        assert sched.phone_waiting() == ["bbbb0001-0"]
        assert sched.phone_attached("bbbb0002-0") is False
        assert sched.phone_attached("bbbb0003-0") is False
        assert sched.phone_attached("nope0000-0") is False
        with sched._cv:
            sched._queue.append("bbbb0001-0")
        assert sched.phone_attached("bbbb0001-0") is False
    finally:
        sched.close()


def test_the_watcher_thread_polls_and_stops(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world, PLAN, phone_turn(world), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement", tag="A")
        watcher = sched.start_phone_watch(interval=0.05)
        assert sched.start_phone_watch() is watcher
        wait(lambda: state(world).stage != "implement")
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
    assert not watcher.is_alive()


def test_a_failing_tick_does_not_kill_the_watcher(world: Env) -> None:
    sched, _ = boot(world)
    try:
        watcher = PhoneWatcher(sched, interval=0.02)

        def boom() -> bool:
            raise RuntimeError("tick")

        watcher.tick = boom  # type: ignore[method-assign]
        watcher.start()
        time.sleep(0.2)
        assert watcher.is_alive()
        watcher.stop()
        watcher.join(timeout=2)
        assert not watcher.is_alive()
    finally:
        sched.close()


def test_idle_engine_has_no_watcher(world: Env) -> None:
    sched, _ = boot(world)
    try:
        assert sched.watcher is None
    finally:
        sched.close()


def test_a_tag_only_wait_with_no_staged_files_can_still_be_attached(world: Env) -> None:
    sched, _ = boot(world, LIVE_OK, done_check="true")
    try:
        waiting_run(world, CARD)
        assert sched.phone_attached(CARD) is True
        wait_stage(world, sched, "gate")
        assert not (world.root / CARD / "live_check.emulator.md").exists()
    finally:
        sched.close()
