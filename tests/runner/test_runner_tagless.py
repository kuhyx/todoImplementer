from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_BAD, LIVE_OK, PLAN, boot, reply, state, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState

NO_TAG = reply("I did some things.")
RUNNING = reply("Background agents still going.\n\nR: waiting on them")
FIX = reply("fixed it\n\nD: done")


def _hook(world: Env, *, always: bool) -> None:
    marker = world.tmp / "hook-ran"
    once = "" if always else f'[ -e "{marker}" ] && exit 0\ntouch "{marker}"\n'
    body = f"#!/bin/sh\n{once}echo 'stdout-line lint'\necho 'stderr-line hook says no' >&2\nexit 1\n"
    hook = world.src / "demo" / ".git" / "hooks" / "pre-commit"
    hook.write_text(body, encoding="utf-8")
    hook.chmod(0o755)


def test_t1220_three_tagless_turns_get_one_fresh_session_retry(world: Env) -> None:
    sched, _ = boot(world, PLAN, NO_TAG, NO_TAG, NO_TAG, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert "tagless_retry" not in st.extra or st.extra["tagless_retry"] is True
        fresh = world.calls()[4]
        assert fresh["resume"] is None
        assert "Handoff summary" in fresh["prompt"]
    finally:
        sched.close()


def test_t1221_a_second_tagless_run_needs_you(world: Env) -> None:
    sched, _ = boot(world, PLAN, NO_TAG, NO_TAG, NO_TAG, NO_TAG, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "without a status tag" in st.error
        assert len(world.calls()) == 5
    finally:
        sched.close()


def test_t1222_an_r_turn_continues_the_same_session_without_a_nudge(world: Env) -> None:
    sched, _ = boot(world, PLAN, RUNNING, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert calls[2]["resume"] == calls[1]["resume"] or calls[2]["resume"] is not None
        assert "background work is done" in calls[2]["prompt"]
        assert "no status tag" not in calls[2]["prompt"]
        assert "nudges" not in st.extra
        assert "r_continues" not in st.extra
    finally:
        sched.close()


def test_t1223_r_continues_are_capped_at_three_then_fall_back_to_nudges(world: Env) -> None:
    sched, _ = boot(world, PLAN, RUNNING, RUNNING, RUNNING, RUNNING, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        calls = world.calls()
        assert "background work is done" in calls[4]["prompt"]
        assert "no status tag" in calls[5]["prompt"]
    finally:
        sched.close()


def test_t1224_retry_resumes_the_failed_stage_not_the_plan(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_BAD, FIX, LIVE_BAD, FIX, LIVE_BAD, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.extra["failed_stage"] == "live_check"
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert len(world.calls()) == 8
        assert "failed_stage" not in st.extra
    finally:
        sched.close()


def test_t1225_retry_of_a_failed_ship_goes_back_to_ready_to_ship(world: Env) -> None:
    sched, _ = boot(world, done_check="true")
    run = RunState(task_id=CARD, stage="failed", error="push refused", extra={"failed_stage": "shipping"})
    store.save(world.root / CARD, run)
    try:
        sched.start(CARD)
        st = state(world)
        assert (st.stage, st.error) == ("gate", None)
        assert not world.calls()
    finally:
        sched.close()


def test_t1226_a_commit_hook_failure_goes_to_a_fix_turn_and_ships_again(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, FIX, done_check="true")
    _hook(world, always=False)
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        sched.ship(CARD)
        st = wait_stage(world, sched, "shipped")
        assert st.extra["ship_fixes"] == 1
        prompt = world.calls()[-1]["prompt"]
        assert "stderr-line hook says no" in prompt
        assert "stdout-line lint" in prompt
        assert client.closed
    finally:
        sched.close()


def test_t1227_ship_fixes_are_capped_and_the_error_omits_the_commit_message(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, FIX, FIX, done_check="true")
    _hook(world, always=True)
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        sched.ship(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "stderr-line hook says no" in st.error
        assert "Todo:" not in st.error
        assert "-m" not in st.error
        assert not client.closed
    finally:
        sched.close()
