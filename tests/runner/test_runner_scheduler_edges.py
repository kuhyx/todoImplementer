import json
import time

import pytest
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import stages, worktree
from todoimpl.runner.scheduler import RunnerError, Scheduler


def _limit(resets_at: float) -> tuple[dict[str, object], ...]:
    return (
        {"_fake": "limit", "resets_at": resets_at},
        {"_fake": "result", "text": "usage limit reached", "is_error": True},
    )


def test_plan_limit_pauses_and_resumes_at_resets_at(world: Env) -> None:
    sched, _ = boot(world, PLAN, _limit(time.time() + 1.0), IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "paused_limit")
        assert state(world).resume_at is not None
        assert (world.root / "limit-until").exists()
        st = wait_stage(world, sched, "gate")
        assert st.resume_at is None
        assert not (world.root / "limit-until").exists()
    finally:
        sched.close()


def test_limit_pauses_every_run_and_credits_lift_one(world: Env) -> None:
    sched, client = boot(world, PLAN, _limit(time.time() + 3600), IMPL, LIVE_OK, done_check="true")
    client.tasks["bbbb2222"] = task("bbbb2222", done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "paused_limit")
        calls = len(world.calls())
        sched.start("bbbb2222-0")
        time.sleep(0.5)
        assert len(world.calls()) == calls
        assert "bbbb2222-0" not in sched.running()
        sched.credits(CARD)
        st = wait_stage(world, sched, "gate")
        assert st.using_credits
        with pytest.raises(RunnerError, match="only while the plan limit"):
            sched.credits(CARD)
        assert state(world, "bbbb2222-0").stage == "plan"
    finally:
        sched.close()


def test_cancel_kills_a_live_turn_and_start_restarts(world: Env) -> None:
    sched, _ = boot(world, PLAN, ({"_fake": "sleep", "sec": 20},), done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: any("Implement" in c["prompt"] for c in world.calls()))
        with pytest.raises(RunnerError, match="already running"):
            sched.start(CARD)
        with pytest.raises(RunnerError, match="has a turn running"):
            sched.ship(CARD)
        started = time.monotonic()
        sched.cancel(CARD)
        wait_stage(world, sched, "cancelled")
        assert time.monotonic() - started < 10
        with pytest.raises(RunnerError, match="already cancelled"):
            sched.cancel(CARD)
        with pytest.raises(RunnerError, match="cancelled: nothing to send"):
            sched.send(CARD, "hi")
        for turn in (PLAN, IMPL, LIVE_OK):
            world.script("abcd1234", *turn)
        sched.start(CARD)
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_unknown_runs_and_wrong_stages_are_refused(world: Env) -> None:
    sched, _ = boot(world)
    try:
        with pytest.raises(RunnerError, match="unknown task") as unknown:
            sched.start("zzzz9999-0")
        assert unknown.value.code == "not_found"
        for action in (sched.ship, sched.cancel, sched.spec_ok, sched.credits):
            with pytest.raises(RunnerError, match="has no run yet"):
                action(CARD)
        with pytest.raises(RunnerError, match="has no run yet"):
            sched.send(CARD, "x")
        assert list(sched.subscribe(CARD, after=0).__class__.__mro__)  # a generator, not started
    finally:
        sched.close()


def test_missing_repo_hands_the_item_to_kuhy(world: Env) -> None:
    sched, _ = boot(world, repo="kuhyx/missing", done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.assignee == "human"
        assert st.error is not None
        assert "not cloned" in st.error
        assert world.calls() == []
    finally:
        sched.close()


def _seed(world: Env, card: str, stage: str, **extra: object) -> RunState:
    st = RunState(task_id=card, stage=stage, **extra)  # type: ignore[arg-type]
    store.save(world.root / card, st)
    return st


def test_recover_resumes_a_killed_turn_and_fails_an_interrupted_ship(world: Env) -> None:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, CARD)
    sessions = {"implement": {"session_id": "s-old", "last_turn_end": time.time()}}
    _seed(world, CARD, "implement", worktree=str(wt.path), branch=wt.branch, sessions=sessions)
    (world.root / CARD / "plan.md").write_text(PLAN[0]["text"], encoding="utf-8")
    init = {"type": "system", "subtype": "init", "session_id": "s-old"}
    (world.root / CARD / "implement-1.000.stream.jsonl").write_text(json.dumps(init) + "\n", encoding="utf-8")
    _seed(world, "cccc3333-0", "shipping")
    _seed(world, "dddd4444-0", "implement")
    (world.root / "eeee5555-0").mkdir()
    (world.root / "eeee5555-0" / "state.json").write_text("{", encoding="utf-8")
    for turn in (IMPL, LIVE_OK):
        world.script("abcd1234", *turn)
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        wait_stage(world, sched, "gate")
        first = world.calls()[0]
        assert first["resume"] == "s-old"
        assert "killed mid-work" in first["prompt"]
        shipped = state(world, "cccc3333-0")
        assert (shipped.stage, shipped.extra["failed_stage"]) == ("failed", "gate")
        lost = wait_stage(world, sched, "failed", "dddd4444-0")
        assert lost.error is not None
        assert "could not be read" in lost.error
    finally:
        sched.close()


def test_idle_session_starts_fresh_with_a_handoff(world: Env) -> None:
    sched, _ = boot(world, PLAN, reply("Q: name?"), IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement")
        st.sessions["implement"]["last_turn_end"] = 0.0
        store.save(world.root / CARD, st)
        sched.send(CARD, "hello.txt")
        wait_stage(world, sched, "gate")
        fresh = world.calls()[2]
        assert fresh["resume"] is None
        assert "Handoff summary" in fresh["prompt"]
    finally:
        sched.close()


def test_a_crashing_turn_needs_you_once_the_retries_are_spent(world: Env) -> None:
    crash = ({"_fake": "exit", "code": 3},)
    sched, _ = boot(world, PLAN, crash, crash, crash, crash, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "claude exited without a result" in st.error
    finally:
        sched.close()


def test_an_api_error_turn_pauses_to_retry_instead_of_failing(world: Env) -> None:
    sched, _ = boot(world, PLAN, reply("API Error: 500", is_error=True), done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "paused_retry")
        assert st.extra["retry_reason"] == "API Error: 500"
    finally:
        sched.close()


def test_plan_without_criteria_and_questions_rest_or_fail(world: Env) -> None:
    sched, _ = boot(
        world, reply("Q: which repo dir?"), reply("I wrote a plan.\n\nD: done"), done_check="true"
    )
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "plan", tag="Q")
        assert st.last_tag == "Q"
        sched.send(CARD, "this one")
        st = wait_stage(world, sched, "failed")
        assert st.error == "plan.md has no `## Acceptance criteria` items: send guidance"
    finally:
        sched.close()


def test_live_check_question_rests(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, reply("Q: the app needs a token"), done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "live_check")
        assert st.last_tag == "Q"
    finally:
        sched.close()


def test_a_crash_in_a_stage_is_reported(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(_d: object) -> str:
        raise RuntimeError("kaboom")

    monkeypatch.setitem(stages.HANDLERS, "plan", boom)
    sched, _ = boot(world, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error == "The runner crashed: RuntimeError('kaboom')"
    finally:
        sched.close()


def test_a_refused_push_fails_and_send_goes_back_to_implement(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        monkeypatch.setenv("GIT_PUSH_ALLOW_ROOT", "/nowhere")
        sched.ship(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error is not None
        assert "was refused" in st.error
        sched.send(CARD, "retry")
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
