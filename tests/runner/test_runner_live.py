"""Live check settling: plan cross-check, deferred rows, partial acceptance with one follow-up, redo."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, cast

import pytest
from runnerfakes import Env, FakeClient
from schedfakes import CARD, IMPL, LIVE_BAD, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.live import NO_CHECKLIST, followup_body, settle, verdict
from todoimpl.runner.parsing import parse_live
from todoimpl.runner.pipeline import Driver

PLAN2 = (
    {
        "_fake": "result",
        "text": "## Acceptance criteria\nC1. I run a, I see x\nC2. I run b, I see y\n\nD: planned",
    },
)
ONE_OF_TWO = reply("- [x] C1: ran a -> saw x\n\nD: done")


def stub(plan: str = "## Acceptance criteria\n- one\n- two\n", client: FakeClient | None = None) -> Any:
    """Return a Driver look-alike: state extras, item, client and the plan text."""
    fake = SimpleNamespace(
        state=SimpleNamespace(extra={}, sessions={"implement": {"session_id": "s"}}),
        item=SimpleNamespace(title="Demo", repo="kuhyx/demo"),
        ctx=SimpleNamespace(client=client or FakeClient()),
        plan_md=lambda: plan,
        save=lambda: None,
    )
    return cast("Driver", fake)


def test_t1103_plan_criterion_missing_from_report_is_not_done() -> None:
    found = verdict(parse_live("- [x] C1: ok\n- [x] C3: ok"), ["a", "b", "c"])
    assert found.done == ["C1", "C3"]
    assert found.open == [("C2", "missing from the live check report")]
    free = verdict(parse_live("- [x] did a thing\n- [ ] did another"), ["a", "b", "c"])
    assert (free.done, free.open_ids) == (["did a thing"], ["did another"])
    assert verdict([], ["a"]).open == []


def test_t1108_deferred_rows_are_neither_done_nor_open() -> None:
    d = stub()
    d.state.extra["live_fixes"] = 1
    report = "- [x] C1: ok\n- [~] C2: after ship: committed"
    assert settle(d, report) == "checks"
    assert d.state.extra["partial"] == {"done": ["C1"], "open": [], "deferred": ["C2"]}
    assert "live_fixes" not in d.state.extra
    assert settle(d, "- [x] C1: ok\n- [x] C2: ok") == "checks"
    assert "partial" not in d.state.extra


def test_t1104_no_checklist_reruns_once_then_asks() -> None:
    d = stub()
    assert settle(d, "R: live-check agent re-running") == "live_check"
    assert d.state.extra["live_redo"] == NO_CHECKLIST
    assert settle(d, "") == "live_check"
    with pytest.raises(NeedsYouError, match="fresh session"):
        settle(d, "")
    assert settle(d, "- [x] C1: ok\n- [x] C2: ok") == "checks"
    assert "live_redone" not in d.state.extra


def test_t1109_partial_after_the_fix_makes_one_follow_up() -> None:
    client = FakeClient()
    d = stub(client=client)
    report = "- [x] C1: ok\n- [ ] C2: broke"
    assert settle(d, report) == "implement"
    assert d.state.extra["failure_tail"] == report
    assert settle(d, report) == "checks"
    assert d.state.extra["partial"] == {"done": ["C1"], "open": ["C2"], "deferred": []}
    assert client.added == [
        (
            "kuhyx/demo",
            "Demo — rest: C2",
            followup_body(verdict(parse_live(report), ["one", "two"]), ["one", "two"]),
        )
    ]
    assert d.state.extra["followup_id"] == "f0llow01"
    assert settle(d, report) == "checks"
    assert len(client.added) == 1
    body = client.added[0][2]
    assert "- C2: two" in body
    assert "live check: broke" in body


def test_t1109_zero_done_retries_fresh_once_then_asks() -> None:
    d = stub()
    d.state.extra["live_fixes"] = 1
    report = "- [ ] C1: nope\n- [ ] C2: nope"
    assert settle(d, report) == "implement"
    assert d.state.extra["zero_done_retry"] == 1
    assert "implement" not in d.state.sessions
    with pytest.raises(NeedsYouError, match="still saw criteria not done: C1, C2"):
        settle(d, report)
    assert d.ctx.client.added == []


def test_followup_body_lists_plan_text_and_notes() -> None:
    found = verdict(parse_live("- [ ] odd: x\n- [ ] C9: y"), ["only"])
    assert followup_body(found, ["only"]).splitlines()[1:] == [
        "- C1: only",
        "  live check: missing from the live check report",
        "- odd: x",
        "  live check: odd: x",
        "- C9",
        "  live check: y",
    ]


def test_t1109_end_to_end_partial_reaches_the_gate(world: Env) -> None:
    sched, client = boot(world, PLAN2, IMPL, ONE_OF_TWO, IMPL, ONE_OF_TWO, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert st.extra["partial"] == {"done": ["C1"], "open": ["C2"], "deferred": []}
        assert st.extra["followup_id"] == "f0llow01"
        assert [title for _, title, _ in client.added] == ["Add hello file — rest: C2"]
    finally:
        sched.close()


def test_t1109_end_to_end_zero_done_retries_then_needs_you(world: Env) -> None:
    turns = [PLAN, IMPL, LIVE_BAD, IMPL, LIVE_BAD, IMPL, LIVE_BAD]
    sched, client = boot(world, *turns, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.error == "The live check still saw criteria not done: C1"
        assert st.extra["zero_done_retry"] == 1
        assert client.added == []
        assert len(world.calls()) == len(turns)
    finally:
        sched.close()


def test_t1104_end_to_end_delegated_live_check_is_rerun(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, reply("status\n\nD: done"), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        assert NO_CHECKLIST in world.calls()[3]["prompt"]
    finally:
        sched.close()


def test_t1228_an_r_live_check_continues_before_any_redo(world: Env) -> None:
    turns = (PLAN, IMPL, reply("agent running\n\nR: waiting"), LIVE_OK)
    sched, _ = boot(world, *turns, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert "background work is done" in calls[3]["prompt"]
        assert NO_CHECKLIST not in calls[3]["prompt"]
        assert "live_redone" not in st.extra
        assert "r_continues" not in st.extra
    finally:
        sched.close()


def test_t1228_a_live_check_that_keeps_ending_r_is_redone_once_after_the_continues(world: Env) -> None:
    running = reply("agent running\n\nR: waiting")
    sched, _ = boot(world, PLAN, IMPL, *([running] * 4), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        calls = world.calls()
        assert NO_CHECKLIST in calls[6]["prompt"]
        assert len(calls) == 7
    finally:
        sched.close()
