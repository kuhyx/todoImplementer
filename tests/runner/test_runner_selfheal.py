import time
from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, make_repo, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait, wait_stage
from todoimpl.board import state as store
from todoimpl.board.state import RunState
from todoimpl.runner import retry
from todoimpl.runner.scheduler import Scheduler

OFFLINE = (
    {"_fake": "stderr", "text": "Error: getaddrinfo ENOTFOUND api.anthropic.com"},
    {"_fake": "exit", "code": 1},
)


def _crash(text: str = "segfault in module x") -> tuple[dict[str, object], ...]:
    return ({"_fake": "stderr", "text": text}, {"_fake": "exit", "code": 1})


def test_t1201_offline_turn_pauses_for_retry_and_resumes(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "BACKOFF", (0.8, 0.8, 0.8))
    sched, _ = boot(world, PLAN, OFFLINE, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "paused_retry")
        st = state(world)
        assert st.extra["resume_stage"] == "implement"
        assert st.extra["retries"] == 1
        assert "ENOTFOUND" in st.extra["retry_reason"]
        assert st.resume_at is not None
        assert st.resume_at > time.time()
        assert len(world.calls()) == 2
        st = wait_stage(world, sched, "gate")
        assert "retries" not in st.extra
        assert len(world.calls()) == 4
    finally:
        sched.close()


def test_t1202_a_crash_retries_three_times_then_needs_you_with_the_stderr(world: Env) -> None:
    long = "x" * 400 + "THE-END"
    sched, _ = boot(world, PLAN, _crash(long), _crash(long), _crash(long), _crash(long), done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert len(world.calls()) == 5
        assert st.error is not None
        assert st.error.startswith("The implement turn failed: claude exited without a result")
        assert st.error.endswith("THE-END)")
        assert len(st.error) < 400
    finally:
        sched.close()


def test_t1203_a_silent_kill_is_a_crash_that_recovers(world: Env) -> None:
    sched, _ = boot(world, PLAN, ({"_fake": "exit", "code": 247},), IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert "crash_retries" not in st.extra
        assert len(world.calls()) == 4
    finally:
        sched.close()


def test_t1204_backoff_is_1_2_5_10_then_every_30_minutes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "BACKOFF", retry.DEFAULT_BACKOFF)
    monkeypatch.setattr(retry, "LONG_WAIT", retry.DEFAULT_LONG_WAIT)
    assert [retry.delay(n) for n in range(7)] == [60, 120, 300, 600, 1800, 1800, 1800]


@pytest.mark.parametrize(
    ("text", "transient"),
    [
        ("getaddrinfo EAI_AGAIN", True),
        ("read ECONNRESET", True),
        ("API Error: 529 overloaded_error", True),
        ("request failed with status 503", True),
        ("Connection error.", True),
        ("Traceback: KeyError 'x' at line 512", False),
        ("", False),
    ],
)
def test_t1205_classification(text: str, *, transient: bool) -> None:
    assert retry.is_transient(text) is transient


def test_t1206_stderr_tail_reads_the_newest_log(tmp_path: Path) -> None:
    assert retry.stderr_tail(tmp_path, "implement") == ""
    (tmp_path / "implement-1.stderr.log").write_text("old\n", encoding="utf-8")
    (tmp_path / "implement-2.stderr.log").write_text("a" * 900 + "new\n", encoding="utf-8")
    assert retry.stderr_tail(tmp_path, "implement").endswith("new")
    assert len(retry.stderr_tail(tmp_path, "implement")) <= retry.TAIL_READ


def test_t1207_unreachable_todo_mcp_pauses_instead_of_failing(world: Env) -> None:
    make_repo(world)
    for turn in (PLAN, IMPL, LIVE_OK):
        world.script("abcd1234", *turn)
    store.save(world.root / CARD, RunState(task_id=CARD, stage="plan"))
    client = FakeClient({"abcd1234": task(done_check="true")}, unreachable=1)
    sched = Scheduler(client, world.root, check_timeout=20)
    try:
        st = wait_stage(world, sched, "paused_retry")
        assert st.extra["resume_stage"] == "plan"
        assert "cannot reach MCP" in st.extra["retry_reason"]
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t1208_restart_recovers_a_paused_retry_and_holds_it_until_resume_at(world: Env) -> None:
    make_repo(world)
    world.script("abcd1234", *IMPL)
    world.script("abcd1234", *LIVE_OK)
    until = time.time() + 1.0
    run = RunState(task_id=CARD, stage="paused_retry", resume_at=until, extra={"resume_stage": "implement"})
    store.save(world.root / CARD, run)
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        time.sleep(0.5)
        assert not world.calls()
        st = wait_stage(world, sched, "gate")
        assert world.calls()
        assert st.resume_at is None
        assert time.time() >= until
    finally:
        sched.close()


def _seed_paused(world: Env, resume_at: float) -> None:
    make_repo(world)
    for turn in (IMPL, LIVE_OK):
        world.script("abcd1234", *turn)
    extra = {"resume_stage": "implement", "retry_reason": "offline"}
    run = RunState(task_id=CARD, stage="paused_retry", resume_at=resume_at, extra=extra)
    store.save(world.root / CARD, run)


def test_t1212_a_second_unreachable_read_keeps_the_stage_to_resume(world: Env) -> None:
    _seed_paused(world, time.time() - 1)
    client = FakeClient({"abcd1234": task(done_check="true")}, unreachable=1)
    sched = Scheduler(client, world.root, check_timeout=20)
    try:
        wait(lambda: state(world).extra.get("retries") == 1)
        st = wait_stage(world, sched, "gate")
        assert st.error is None
    finally:
        sched.close()


def test_t1213_a_note_from_kuhy_ends_the_wait_at_once(world: Env) -> None:
    _seed_paused(world, time.time() + 3600)
    sched = Scheduler(FakeClient({"abcd1234": task(done_check="true")}), world.root, check_timeout=20)
    try:
        time.sleep(0.3)
        assert not world.calls()
        sched.send(CARD, "go on")
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
