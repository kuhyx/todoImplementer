"""The live check is verify-and-report work: its own Sonnet session, seeded from the handoff."""

from __future__ import annotations

from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_BAD, LIVE_OK, PLAN, boot, wait_stage

PLAN_CRITERION = "C1. I run `cat hello.txt`, I see hi"


def test_t1896_the_live_check_runs_on_sonnet_in_a_fresh_session_seeded_from_the_handoff(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        plan, impl, live = world.calls()
        assert (impl["model"], live["model"]) == ("opus", "sonnet")
        assert live["resume"] is None  # not the implementer's conversation: no whole-transcript cache write
        assert "Live check stage" in live["prompt"]
        assert (
            "C1: done - cat shows hi" in live["prompt"]
        )  # the implementer's own last reply, from the handoff
        assert (
            live["prompt"].count(PLAN_CRITERION) == 1
        )  # the plan once: in the prompt, not again in the handoff
        assert set(st.sessions) == {"plan", "implement", "live_check"}
        assert plan["model"] == "sonnet"
    finally:
        sched.close()


def test_t1896_a_failed_live_check_resumes_the_implementer_without_the_plan_text_and_checks_in_a_new_session(
    world: Env,
) -> None:
    sched, _ = boot(world, PLAN, IMPL, LIVE_BAD, IMPL, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        _, _, live1, fix, live2 = world.calls()
        assert fix["model"] == "opus"
        assert fix["resume"] == st.sessions["implement"]["session_id"]  # the implement session continues
        assert PLAN_CRITERION not in fix["prompt"]  # T1891: the resumed session already holds plan.md
        assert "plan.md" in fix["prompt"]
        assert live2["resume"] is None  # a new check of the new work: a new session
        assert live2["model"] == live1["model"] == "sonnet"
    finally:
        sched.close()


def test_t1896_the_phone_and_checklist_follow_ups_resume_the_live_session(world: Env) -> None:
    summary = ({"_fake": "result", "text": "All verified.\n\nD: done"},)
    sched, _ = boot(world, PLAN, IMPL, summary, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        _, _, live, redo = world.calls()
        assert live["resume"] is None
        assert "Do not re-run" in redo["prompt"]
        assert redo["model"] == "sonnet"
        assert (
            redo["resume"] == st.sessions["live_check"]["session_id"]
        )  # the same live session, not implement
        assert redo["resume"] != st.sessions["implement"]["session_id"]
    finally:
        sched.close()
