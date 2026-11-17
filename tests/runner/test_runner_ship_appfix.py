"""App-error runs: ship and deploy themselves, mark the ledger, wait for the phone when it is away."""

import pytest
from contract_lib import validate
from phonefakes import SERIAL, fake_adb
from runnerfakes import Env, FakeClient, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait_stage
from todoimpl.board import state as store
from todoimpl.board import status as board_status
from todoimpl.board.state import RunState
from todoimpl.errors import ledger
from todoimpl.runner import appfix
from todoimpl.runner.phone_sched import PhoneEngine, PhoneWatcher
from todoimpl.runner.scheduler import Scheduler

WAIT = {"since": 1.0, "tries": 1}
BODY = "done: hello.txt exists\nError-Signature: demo:aaa"
MARK = {"app_error": {"reason": "weekly", "keys": ["demo:aaa"], "at": 1.0}}


def _ticket(world: Env) -> None:
    ledger.put(world.root, "demo:aaa", state="ticket", repo="kuhyx/demo", title="t", count=1, starts=1)


def _status(world: Env) -> board_status.Status:
    return board_status.compute(task(body=BODY), state(world), live=False, limit_until=None)


def _run_to_deploy(world: Env, monkeypatch: pytest.MonkeyPatch, code: int, *, adb: bool) -> Scheduler:
    """Run an error card to its deploy (exit `code`); the Pixel is attached or missing. The caller closes."""
    monkeypatch.setenv("DEPLOY_EXIT", str(code))
    if adb:
        fake_adb(world, f"{SERIAL} device")
    else:
        monkeypatch.setenv("TODOIMPL_ADB", str(world.tmp / "no-adb-here"))
    _ticket(world)
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, body=BODY)
    sched.start(CARD, auto_ship=True, extra=MARK)
    wait_stage(world, sched, "failed")
    return sched


def test_t2020_an_error_card_ships_itself_without_a_done_check_and_marks_the_ledger(world: Env) -> None:
    _ticket(world)
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, body=BODY)
    try:
        sched.start(CARD, auto_ship=True, extra=MARK)
        st = wait_stage(world, sched, "shipped")
        validate("state", st.to_dict())
        assert st.ship is not None
        assert len(client.closed) == 1
        entry = ledger.load(world.root)["demo:aaa"]
        assert (entry["state"], entry["commit"]) == ("shipped", st.ship["commit"])
    finally:
        sched.close()


def test_t2020_a_run_that_is_not_an_error_card_still_rests_at_the_gate(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, body=BODY)
    try:
        sched.start(CARD, auto_ship=True)
        wait_stage(world, sched, "gate")
        assert client.closed == []
        assert ledger.load(world.root) == {}
    finally:
        sched.close()


def test_t2021_a_deploy_that_finds_no_phone_waits_for_it_with_its_own_status(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched = _run_to_deploy(
        world, monkeypatch, 30, adb=True
    )  # phone_deploy exit 30: the phone was unreachable
    sched.close()
    st = state(world)
    assert st.error is not None
    assert st.error.startswith("pushed, not deployed")
    assert st.extra["phone_update"]["tries"] == 1
    assert _status(world) == board_status.Status.WAITING_PHONE_UPDATE
    assert ledger.load(world.root)["demo:aaa"]["state"] == "ticket"  # nothing is fixed until it is installed


def test_t2021_any_failed_deploy_with_no_adb_device_waits_for_the_phone(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_to_deploy(world, monkeypatch, 3, adb=False).close()
    assert "phone_update" in state(world).extra
    assert _status(world) == board_status.Status.WAITING_PHONE_UPDATE


def test_t2021_a_failed_deploy_with_the_phone_attached_needs_kuhy(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _run_to_deploy(world, monkeypatch, 3, adb=True).close()
    assert "phone_update" not in state(world).extra
    assert _status(world) == board_status.Status.NEEDS_YOU


def test_t2021_a_card_that_is_not_an_error_card_never_waits_for_the_phone_on_exit_3(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    monkeypatch.setenv("TODOIMPL_ADB", str(world.tmp / "no-adb-here"))
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, body=BODY)
    try:
        sched.start(CARD, auto_ship=True)
        wait_stage(world, sched, "gate")
        sched.ship(CARD)
        st = wait_stage(world, sched, "failed")
        assert "phone_update" not in st.extra
    finally:
        sched.close()


def test_t2022_the_phone_appearing_reruns_the_deploy_and_finishes_the_card(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DEPLOY_EXIT", "30")
    fake_adb(world, f"{SERIAL} device")
    _ticket(world)
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, body=BODY)
    try:
        sched.start(CARD, auto_ship=True, extra=MARK)
        wait_stage(world, sched, "failed")
        assert sched.phone_updates() == [CARD]
        monkeypatch.setenv("DEPLOY_EXIT", "0")  # the phone is back
        assert PhoneWatcher(sched).tick() is True
        st = wait_stage(world, sched, "shipped")
        assert "phone_update" not in st.extra
        assert len(client.closed) == 1
        assert ledger.load(world.root)["demo:aaa"]["state"] == "shipped"
        assert sched.phone_updates() == []
    finally:
        sched.close()


def test_t2022_with_no_phone_attached_the_wait_goes_on(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    sched = _run_to_deploy(world, monkeypatch, 30, adb=False)
    try:
        assert sched.phone_updates() == [CARD]
        assert PhoneWatcher(sched).tick() is False
        assert state(world).stage == "failed"
    finally:
        sched.close()


def test_t2022_a_wait_that_keeps_failing_ends_with_kuhy_after_five_tries(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched = _run_to_deploy(world, monkeypatch, 30, adb=True)
    try:
        for tries in range(2, 6):
            assert sched.phone_update_start(CARD) is True
            st = wait_stage(world, sched, "failed")
            assert st.extra["phone_update"]["tries"] == tries
        assert sched.phone_update_start(CARD) is True
        st = wait_stage(world, sched, "failed")
        assert "phone_update" not in st.extra  # the sixth failure is plain
        assert sched.phone_updates() == []
    finally:
        sched.close()


def test_t2022_a_card_that_no_longer_waits_is_not_restarted(world: Env) -> None:
    sched, _ = boot(world)
    try:
        assert sched.phone_update_start(CARD) is False  # no run at all
        store.save(world.root / CARD, RunState(task_id=CARD, stage="failed"))
        assert sched.phone_update_start(CARD) is False  # failed, but not for the phone
    finally:
        sched.close()


def test_a_new_cycle_forgets_the_error_mark_and_the_phone_tries(world: Env) -> None:
    sched, _ = boot(world)
    try:
        extra = {**MARK, "phone_tries": 3}
        store.save(world.root / CARD, RunState(task_id=CARD, stage="cancelled", extra=extra))
        sched.start(CARD)
        assert not {"app_error", "phone_tries"} & set(state(world).extra)
    finally:
        sched.close()


def test_a_start_can_mark_the_run(world: Env) -> None:
    sched, _ = boot(world)
    try:
        sched.start(CARD, extra=MARK)
        assert state(world).extra["app_error"] == MARK["app_error"]
    finally:
        sched.close()


def test_the_bare_phone_engine_cannot_start_a_ship(world: Env) -> None:
    engine = PhoneEngine(FakeClient({"abcd1234": task()}), world.root, 1.0, lambda: 1.0)
    try:
        assert engine.phone_update_start(CARD) is False
        assert engine.phone_updates() == []
    finally:
        engine.close()


def test_a_shipped_part_without_a_signature_marks_nothing(world: Env) -> None:
    item = FakeClient({"abcd1234": task(body="a plain part")}).item("abcd1234")
    appfix.shipped(world.root, world.root / CARD, item, "abc", 1.0)
    assert ledger.load(world.root) == {}


def test_a_waiting_card_whose_note_is_gone_is_not_restarted(world: Env) -> None:
    sched, _ = boot(world)
    try:
        gone = RunState(task_id="zzzz9999-0", stage="failed", extra={"phone_update": WAIT})
        store.save(world.root / "zzzz9999-0", gone)
        assert sched.phone_update_start("zzzz9999-0") is False
    finally:
        sched.close()
