"""T2104: an `A:` of commands and waits Claude can do rests on the backoff, then resumes."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from phonefakes import SERIAL, fake_adb, phone_turn
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board.needs import needs
from todoimpl.board.state import RunState
from todoimpl.board.status import Status, compute
from todoimpl.runner import resume, retry, scheduler
from todoimpl.umbrella import run as umbrella_run

TUTOR = (
    "phone: C7 is not verified. Resume by checking `systemctl --user is-active tutor-slot-build2`. "
    "When it finishes, run `phone_vd.sh start com.kuhy.slot8` and read the screen. "
    "Then run `phone_slot.sh release`."
)
SELF = [
    TUTOR,
    "Resume by rerunning `make fast` once the build unit is done",
    "The build is still running. Resume with `journalctl --user -u build | tail`, then run the checks",
]
KUHY = [
    "Resume by telling me which layout you want",
    "Resume once you click Ship on the card",
    "Plug in the Pixel: the app passed on the emulator",
    "Resume by plugging in the Pixel, then run the checks",
    "Resume by adding your GitHub token to the repo secrets",
    "Which of the two layouts do you want for the header?",
    "Run `deploy-todoimpl`, then rerun this card's checks",  # a plain command is grant.py's, not a wait
    "",
]
CHOICE = "A: pick one\n\n```ask\nchoice c1: Layout | wide | *narrow | risk=reversible\n```"


@pytest.mark.parametrize("ask", SELF)
def test_t2104_resume_text_made_of_commands_and_waits_is_self_resumable(ask: str) -> None:
    assert resume.is_self_resume(ask, f"A: {ask}")


@pytest.mark.parametrize("ask", KUHY)
def test_t2104_asks_that_need_kuhy_are_not(ask: str) -> None:
    assert not resume.is_self_resume(ask, f"A: {ask}")


def test_t2104_an_ask_block_with_a_choice_is_kuhys() -> None:
    assert not resume.is_self_resume("Resume by running make fast", CHOICE)


def _driver(
    ask: str = TUTOR, tag: str = "A", extra: dict[str, Any] | None = None, **more: Any
) -> tuple[Any, list[int], list[str]]:
    saved: list[int] = []
    said: list[str] = []
    st = RunState(
        task_id="x-0",
        stage="live_check",
        last_tag=tag,
        extra={"last_reply": f"{tag}: {ask}", **(extra or {}), **more},
    )
    ctx = SimpleNamespace(now=lambda: 1000.0, run_dir=None)
    driver = SimpleNamespace(state=st, ctx=ctx, activity=said.append, save=lambda: saved.append(1))
    return driver, saved, said


def _res(tag: str = "A", *, error: bool = False) -> Any:
    return SimpleNamespace(tag=tag, is_error=error, denials=[])


def test_t2104_the_card_rests_on_the_ladder_with_the_ask_as_the_next_prompt(tmp_path: Any) -> None:
    driver, saved, said = _driver(waiting_phone={"tried_attached": True, "note": TUTOR})
    driver.ctx.run_dir = tmp_path
    (tmp_path / "phone_ready.json").write_text("{}", encoding="utf-8")
    with pytest.raises(retry.RetryLaterError) as hit:
        resume.rest(driver, _res(), "live_check")
    until, why = hit.value.args
    assert until == 1000.0 + retry.delay(0)
    assert "tutor-slot-build2" in why
    st = driver.state
    assert st.extra[resume.KEY] == 1
    assert TUTOR in st.extra["granted_note"]
    assert st.extra["granted_note"].startswith("(runner) Resume it yourself")
    assert st.last_tag is None
    assert st.extra["waiting_phone"]["tried_attached"] is True  # the next `A: phone:` stays no cable ask
    assert not (tmp_path / "phone_ready.json").exists()
    assert saved == [1]
    assert said


def test_t2104_each_rest_takes_the_next_ladder_step(tmp_path: Any) -> None:
    driver, _, _ = _driver(extra={resume.KEY: 3})
    driver.ctx.run_dir = tmp_path
    with pytest.raises(retry.RetryLaterError) as hit:
        resume.rest(driver, _res(), "live_check")
    assert hit.value.args[0] == 1000.0 + retry.delay(3)


@pytest.mark.parametrize(
    ("stage", "tag", "extra"),
    [
        ("live_check", "A", {resume.KEY: resume.MAX_RESUMES}),  # out of passes: the card parks
        ("spec", "A", {}),
        ("plan", "A", {}),
        ("live_check", "R", {}),
        ("live_check", "Q", {}),
        ("live_check", "A", {"waiting_phone": {"note": "plug in"}}),  # the cable ask is kuhy's
    ],
)
def test_t2104_it_leaves_everything_else_alone(stage: str, tag: str, extra: dict[str, Any]) -> None:
    driver, saved, _ = _driver(tag=tag, extra=extra)
    resume.rest(driver, _res(tag), stage)
    assert saved == []
    assert "granted_note" not in driver.state.extra


def test_t2104_a_failed_turn_or_an_unrelated_ask_is_left_alone() -> None:
    driver, saved, _ = _driver()
    resume.rest(driver, _res(error=True), "live_check")
    other, _, _ = _driver("Which layout do you want?")
    resume.rest(other, _res(), "live_check")
    assert saved == []


def test_t2104_start_retry_and_a_note_clear_the_resume_count() -> None:
    assert resume.KEY in scheduler.COUNTERS
    assert resume.KEY in scheduler.RESET
    assert resume.KEY in umbrella_run.COUNTERS


def test_t2104_the_tutor_card_resumes_by_itself_instead_of_parking(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retry, "BACKOFF", (0.8, 0.8, 0.8))
    fake_adb(world, f"{SERIAL} device")
    tutor = reply(f"The build is still running.\n\nA: {TUTOR}")
    sched, _ = boot(world, PLAN, IMPL, phone_turn(world), tutor, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: state(world).stage == "paused_retry")
        st = state(world)
        assert st.extra["resume_stage"] == "live_check"
        assert st.extra[resume.KEY] == 1
        assert "tutor-slot-build2" in st.extra["retry_reason"]
        quiet = False  # no runner thread is live while the run rests
        assert compute(SimpleNamespace(status="open", title="t"), st, quiet, None) == Status.WORKING
        st = wait_stage(world, sched, "gate")
        prompts = [call["prompt"] for call in world.calls()]
        assert "(runner) Resume it yourself" in prompts[-1]
        assert "phone_slot.sh release" in prompts[-1]
        assert "(runner) Resume it yourself" not in prompts[3]
    finally:
        sched.close()


def test_t2104_a_card_that_keeps_waiting_parks_after_the_last_pass(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retry, "BACKOFF", (0.1,))
    monkeypatch.setattr(retry, "LONG_WAIT", 0.1)
    monkeypatch.setattr(resume, "MAX_RESUMES", 2)
    fake_adb(world, f"{SERIAL} device")
    wait_ask = reply(f"Still building.\n\nA: {TUTOR}")
    sched, _ = boot(world, PLAN, IMPL, phone_turn(world), wait_ask, wait_ask, wait_ask, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "live_check", tag="A", turns=3)
        assert st.extra[resume.KEY] == 2
        assert needs(st).kind == "claude_action"
        assert "tutor-slot-build2" in needs(st).text
    finally:
        sched.close()
