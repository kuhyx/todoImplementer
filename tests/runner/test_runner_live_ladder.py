"""A live check without a checklist: format-only redo, then a fresh session, then kuhy (T1808)."""

from __future__ import annotations

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from test_runner_live import stub
from todoimpl.runner.files import NeedsYouError
from todoimpl.runner.live import NO_CHECKLIST, settle

SUMMARY = reply("All verified, nothing else to say.\n\nD: done")


def test_t1808_the_second_empty_report_starts_a_fresh_session_before_asking() -> None:
    d = stub()
    assert settle(d, "summary") == "live_check"
    assert d.state.extra["live_redo"] == NO_CHECKLIST
    assert settle(d, "summary again") == "live_check"
    assert "live_redo" not in d.state.extra
    assert "live_check" not in d.state.sessions  # the live check starts again in a new session
    assert "implement" in d.state.sessions
    with pytest.raises(NeedsYouError, match="fresh session"):
        settle(d, "")


def test_t1808_end_to_end_two_summaries_then_a_fresh_live_check_passes(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, SUMMARY, SUMMARY, LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert "Do not re-run" in calls[3]["prompt"]
        assert calls[3]["resume"] is not None
        assert calls[4]["resume"] is None
        assert "Live check stage" in calls[4]["prompt"]
        assert "live_redone" not in st.extra
    finally:
        sched.close()
