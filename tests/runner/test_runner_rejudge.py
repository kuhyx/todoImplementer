"""Failed live checks are judged again from their stored report on every start, spending no tokens."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from runnerfakes import FakeClient
from schedfakes import CARD, IMPL, boot, reply, state, wait_stage
from todoimpl.board import state as store
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.live import rejudge, settle
from todoimpl.runner.retry import RetryLaterError
from todoimpl.runner.scheduler import Scheduler

if TYPE_CHECKING:
    from runnerfakes import Env
    from todoimpl.runner.pipeline import Driver

PLAN2 = reply("## Acceptance criteria\nC1. I run a, I see x\nC2. I run b, I see y\n\nD: planned")
ONE_OF_TWO = reply("- [x] C1: ran a -> saw x\n- [ ] C2: no phone\n\nD: done")
OLD_ERROR = "The live check still saw criteria not done: C2"


def _fail_like_before(world: Env, report: str) -> None:
    """Rewrite the rested run as the pre-5c5bfe9 rule left it: failed at live_check, no follow-up."""
    st = state(world)
    st.stage, st.error = "failed", OLD_ERROR
    st.live_check = {"report_md": report, "shots": []}
    for key in ("partial", "followup_id"):
        st.extra.pop(key, None)
    st.extra.update(failed_stage="live_check", live_fixes=1)
    store.save(world.root / CARD, st)


def _ran_to_gate(world: Env) -> tuple[Scheduler, FakeClient]:
    sched, client = boot(world, PLAN2, IMPL, ONE_OF_TWO, IMPL, ONE_OF_TWO, done_check="true")
    sched.start(CARD)
    wait_stage(world, sched, "gate")
    sched.close()
    client.added.clear()
    return sched, client


def test_t1809_failed_live_check_with_a_done_criterion_is_rejudged_on_start(world: Env) -> None:
    _, client = _ran_to_gate(world)
    _fail_like_before(world, "- [x] C1: ran a -> saw x\n- [ ] C2: no phone")
    turns = len(world.calls())
    sched = Scheduler(client, world.root, check_timeout=20)
    try:
        st = wait_stage(world, sched, "gate")
        assert st.error is None
        assert st.extra["partial"] == {"done": ["C1"], "open": ["C2"], "deferred": []}
        assert [title for _, title, _ in client.added] == ["Add hello file — rest: C2"]
        assert len(world.calls()) == turns
    finally:
        sched.close()


def test_t1809_zero_done_stays_in_needs_you_after_a_start(world: Env) -> None:
    _, client = _ran_to_gate(world)
    _fail_like_before(world, "- [ ] C1: nope\n- [ ] C2: nope")
    turns = len(world.calls())
    Scheduler(client, world.root, check_timeout=20).close()
    st = state(world)
    assert (st.stage, st.error) == ("failed", OLD_ERROR)
    assert client.added == []
    assert len(world.calls()) == turns


def _stub(client: FakeClient) -> Any:
    fake = SimpleNamespace(
        state=SimpleNamespace(extra={"live_fixes": 1}, sessions={}),
        item=SimpleNamespace(title="Demo", repo="kuhyx/demo"),
        ctx=SimpleNamespace(client=client, now=lambda: 100.0),
        plan_md=lambda: "## Acceptance criteria\n- one\n- two\n",
        save=lambda: None,
    )
    return cast("Driver", fake)


def test_t1810_follow_up_failure_retries_on_a_timer_not_needs_you() -> None:
    d = _stub(FakeClient(fail_add=1))
    with pytest.raises(RetryLaterError):
        settle(d, "- [x] C1: ok\n- [ ] C2: broke")
    assert d.state.extra["resettle"] is True
    assert "followup_id" not in d.state.extra


def test_t1810_follow_up_retry_spends_no_turn(world: Env) -> None:
    sched, client = boot(world, PLAN2, IMPL, ONE_OF_TWO, IMPL, ONE_OF_TWO, done_check="true")
    client.fail_add = 2
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        assert st.extra["followup_id"] == "f0llow01"
        assert "resettle" not in st.extra
        assert len(world.calls()) == 5
    finally:
        sched.close()


def test_t1809_rejudge_without_a_done_criterion_spends_no_turn() -> None:
    d = _stub(FakeClient())
    d.state.extra["resettle"] = True
    d.state.live_check = {"report_md": "- [ ] C1: nope"}
    with pytest.raises(NeedsYouError, match="none done"):
        rejudge(d)
    assert "resettle" not in d.state.extra
