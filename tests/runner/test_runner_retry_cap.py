"""The transient-retry loop is bounded: after MAX_RETRIES attempts the run rests as failed with the reason."""

from __future__ import annotations

import pytest
from runnerfakes import Env
from schedfakes import CARD, PLAN, boot, wait_stage
from todoimpl.board.state import RunState
from todoimpl.runner import retry
from todoimpl.runner.files import NeedsYouError

OVERLOADED = (
    {"_fake": "stderr", "text": "API Error: 529 overloaded_error"},
    {"_fake": "exit", "code": 1},
)


def _state(retries: int) -> RunState:
    return RunState(task_id="abcd1234-0", stage="implement", extra={"retries": retries})


def test_t1890_a_server_side_api_error_gives_up_after_the_cap_with_its_reason() -> None:
    st = _state(retry.MAX_API_RETRIES - 1)
    last = retry.failure(st, now=0.0, stage="implement", reason="API Error: 529 overloaded", tail="")
    assert isinstance(last, retry.RetryLaterError)
    over = retry.failure(st, now=0.0, stage="implement", reason="API Error: 529 overloaded", tail="")
    assert isinstance(over, NeedsYouError)
    assert over.kind == "run_failed"
    assert f"{retry.MAX_API_RETRIES} automatic retries" in over.text
    assert "overloaded" in over.text


def test_t1890_a_lost_connection_is_an_outage_and_waits_without_end() -> None:
    """DOCS-resilience.md: network outages are waited out on the ladder for ever."""
    st = _state(1000)
    wait = retry.failure(
        st, now=0.0, stage="implement", reason="getaddrinfo ENOTFOUND api.anthropic.com", tail=""
    )
    assert isinstance(wait, retry.RetryLaterError)


def test_t1890_later_stays_uncapped_for_the_waits_that_spend_no_tokens() -> None:
    """The todo-app wait and the live follow-up note retry on a timer for ever (DOCS-spec, Q4)."""
    st = _state(retry.MAX_API_RETRIES + 5)
    wait = retry.later(st, 0.0, "follow-up note not added yet")
    assert isinstance(wait, retry.RetryLaterError)
    assert st.extra["retries"] == retry.MAX_API_RETRIES + 6


@pytest.mark.parametrize(
    ("text", "transient"),
    [
        ("API Error: 400 invalid_request_error: prompt is too long", False),
        ("API Error: 401 authentication_error", False),
        ("Command timed out after 120s", False),
        ("API Error: 500 internal server error", True),
        ("API Error: Request timed out.", True),
        ("API Error: Connection error.", True),
        ("ETIMEDOUT 10.0.0.1:443", True),
    ],
)
def test_t1890_bare_api_error_and_timed_out_no_longer_retry_forever(text: str, *, transient: bool) -> None:
    assert retry.is_transient(text) is transient


def test_t1890_a_turn_the_api_keeps_rejecting_ends_failed_with_the_reason(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(retry, "MAX_API_RETRIES", 2)
    sched, _ = boot(world, PLAN, *([OVERLOADED] * 3), done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "failed")
        assert st.extra["retries"] == 2
        assert "Gave up after 2 automatic retries" in str(st.error)
        assert "overloaded" in str(st.error)
    finally:
        sched.close()
