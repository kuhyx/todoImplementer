import subprocess
import time
from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState, SpecQuestion
from todoimpl.runner import files, limits
from todoimpl.runner.scheduler import RunnerError, Scheduler
from todoimpl.runner.stages import merge_questions
from todoimpl.service.cards import CardTask


def test_merge_questions_keeps_answers_and_renumbers_reused_ids() -> None:
    old = [SpecQuestion("Q1", "Scope", answer="a"), SpecQuestion("Q2", "Style")]
    new = [
        SpecQuestion("Q1", "Scope"),
        SpecQuestion("Q2", "Style v2"),
        SpecQuestion("Q1", "Other"),
        SpecQuestion("Q5", "New"),
    ]
    merged = merge_questions(old, new)
    assert [(q.id, q.title, q.answer) for q in merged] == [
        ("Q1", "Scope", "a"),
        ("Q2", "Style v2", None),
        ("Q3", "Other", None),
        ("Q5", "New", None),
    ]


def test_new_stream_bumps_a_taken_name(tmp_path: Path) -> None:
    run_dir = tmp_path
    first = files.new_stream(run_dir, "plan", 5.0)
    first.write_text("", encoding="utf-8")
    assert files.new_stream(run_dir, "plan", 5.0).name == "plan-5.001.stream.jsonl"


def test_spec_answers_one_at_a_time(world: Env) -> None:
    grill = reply("❓ **Q1** - **A**: a?\n➡️ yes\n❓ **Q2** - **B**: b?\n➡️ no\n\nQ: answer")
    sched, _ = boot(world, grill, reply("D: ok"), reply("D: ok"), body="vague")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "spec_wait")
        sched.spec_answers(CARD, {"Q1": "yes"})
        wait_stage(world, sched, "spec_wait")
        with pytest.raises(RunnerError, match="1 question"):
            sched.spec_ok(CARD)
        sched.spec_answers(CARD, {"Q2": "no"})
        st = wait_stage(world, sched, "spec_wait")
        assert [q.answer for q in st.spec_questions] == ["yes", "no"]
        world.script("abcd1234", *reply("D: still fine"))
        sched.send(CARD, "keep it small")
        wait_stage(world, sched, "spec_wait")
        assert "keep it small" in world.calls()[-1]["prompt"]
    finally:
        sched.close()


def test_limit_seen_mid_run_pauses_the_next_turn_and_credits_resume_it(world: Env) -> None:
    slow = ({"_fake": "sleep", "sec": 1.0}, *IMPL)
    sched, client = boot(world, PLAN, slow, LIVE_OK, done_check="true")
    client.tasks["bbbb2222"] = task("bbbb2222", done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: len(world.calls()) == 2)
        limits.write_until(world.root, time.time() + 3600)
        st = wait_stage(world, sched, "paused_limit")
        assert st.extra["resume_stage"] == "live_check"
        sched.start("bbbb2222-0")
        sched.cancel("bbbb2222-0")
        assert state(world, "bbbb2222-0").stage == "cancelled"
        sched.credits(CARD)
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_credits_drop_once_the_limit_lifted(world: Env) -> None:
    limit = ({"_fake": "limit", "resets_at": time.time() + 3600}, *reply("x", is_error=True))
    sched, _ = boot(world, PLAN, limit, IMPL,
                    LIVE_OK, done_check="true")  # fmt: skip
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "paused_limit")
        st.using_credits = True
        store.save(world.root / CARD, st)
        limits.clear(world.root)
        with sched._cv:
            sched._cv.notify_all()
        st = wait_stage(world, sched, "gate")
        assert not st.using_credits
    finally:
        sched.close()


def test_cancel_between_stages_and_start_conflicts(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="sleep 1")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "checks")
        sched.cancel(CARD)
        wait_stage(world, sched, "cancelled")
        world.script("abcd1234", *PLAN)
        world.script("abcd1234", *reply("Q: hm"))
        sched.start(CARD)
        wait_stage(world, sched, "implement")
        with pytest.raises(RunnerError, match="already has a run"):
            sched.start(CARD)
    finally:
        sched.close()


def test_a_result_without_a_session_keeps_the_old_one(world: Env) -> None:
    sched, _ = boot(world, ({"_fake": "bare"}, *PLAN), IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert "plan" not in st.sessions
    finally:
        sched.close()


def test_engine_internals_survive_odd_states(world: Env) -> None:
    make_repo(world)
    store.save(world.root / "gggg7777-0", RunState(task_id="gggg7777-0", stage="gate"))
    sched = Scheduler(FakeClient({}), world.root)
    try:
        (world.root / "hhhh8888-0").mkdir()
        (world.root / "hhhh8888-0" / "state.json").write_text("{", encoding="utf-8")
        assert not sched._credited("hhhh8888-0")
        sched._drive("none0000-0")
        with sched._cv:
            sched.kill("none0000-0")
        proc = subprocess.Popen(["sleep", "30"], start_new_session=True, text=True)
        sched._register("none0000-0", proc)
        wait(lambda: proc.poll() is not None)
        assert sched.running() == set()
        assert "gggg7777-0" not in sched._queue
    finally:
        sched.close()


class ExplodingClient(FakeClient):
    def get_task(self, card: str) -> CardTask:
        raise RuntimeError(card)


def test_a_drive_that_raises_is_logged_and_released(world: Env) -> None:
    store.save(world.root / CARD, RunState(task_id=CARD, stage="implement"))
    sched = Scheduler(ExplodingClient(), world.root)
    try:
        wait(lambda: not sched._queue and not sched.running())
        assert state(world).stage == "implement"
    finally:
        sched.close()


def test_a_note_sent_mid_turn_reopens_the_resting_run(world: Env) -> None:
    slow_question = ({"_fake": "sleep", "sec": 1.5}, *reply("Q: name?"))
    sched, _ = boot(world, PLAN, slow_question, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: CARD in sched.running() and len(world.calls()) == 2)
        sched.send(CARD, "name it hello.txt")
        wait_stage(world, sched, "gate")
        assert "name it hello.txt" in world.calls()[2]["prompt"]
    finally:
        sched.close()


def test_t301_resumed_turns_add_only_the_cost_delta(world: Env) -> None:
    impl = ({"_fake": "write", "path": "hello.txt", "text": "hi\n"}, *reply("C1: done\n\nD: done", cost=0.03))
    live = reply("- [x] C1: saw hi\n\nD: done", cost=0.045)
    sched, _ = boot(world, PLAN, reply("Q: name?", cost=0.01), impl, live, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement")
        sched.send(CARD, "hello.txt")
        st = wait_stage(world, sched, "gate")
        assert st.cost_usd == 0.055
    finally:
        sched.close()


def test_t302_recover_leaves_runs_waiting_on_kuhy_alone(world: Env) -> None:
    store.save(world.root / CARD, RunState(task_id=CARD, stage="implement", last_tag="Q"))
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root)
    try:
        assert CARD not in sched._queue
        time.sleep(0.3)
        assert world.calls() == []
        assert state(world).stage == "implement"
    finally:
        sched.close()
