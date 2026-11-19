# ruff: noqa: S108
"""actions(): enabled only if it can succeed now, otherwise disabled with the missing thing named."""

import itertools
from typing import Any

import pytest
from board_helpers import EXHAUSTED, LIMITED, NOW, STAGES, TAKEOVER, Note, run
from contract_lib import validate
from todoimpl.board.actions import actions
from todoimpl.board.button import Action
from todoimpl.board.state import RunState, SpecQuestion
from todoimpl.board.status import Status, compute
from todoimpl.board.types import Limit, fmt_when

NO_LIMIT = Limit()
S = Status


def acts(
    status: Status,
    state: RunState | None,
    *,
    limit: Limit = NO_LIMIT,
    note: Note | None = None,
    missing: str | None = None,
) -> dict[str, Action]:
    got = actions(note or Note(), state, status, limit, repo_missing=missing, now=NOW)
    return {a.id: a for a in got}


def test_backlog_start_is_enabled() -> None:
    start = acts(S.BACKLOG, None)["start"]
    assert (start.enabled, start.reason, start.label) == (True, None, "Start")


def test_start_disabled_by_the_usage_limit_with_the_clock_time() -> None:
    start = acts(S.BACKLOG, None, limit=LIMITED)["start"]
    assert start.reason == f"usage limit until {fmt_when(LIMITED.until or 0, NOW)}"


def test_limit_without_end_time() -> None:
    assert acts(S.BACKLOG, None, limit=Limit(active=True))["start"].reason == "usage limit"


def test_start_disabled_when_repo_missing_and_when_note_has_no_repo() -> None:
    assert acts(S.BACKLOG, None, missing="~/src/x")["start"].reason == "repo ~/src/x not found"
    assert acts(S.BACKLOG, None, note=Note(repo=None))["start"].reason == "note has no repo"


def test_cancelled_offers_restart() -> None:
    assert acts(S.CANCELLED, run(stage="cancelled"))["start"].label == "Restart"


def test_free_credits_take_over_so_start_is_not_blocked_by_the_limit() -> None:
    assert acts(S.BACKLOG, None, limit=TAKEOVER)["start"].enabled
    resume = acts(S.NEEDS_YOU, run(error="x"), limit=TAKEOVER)["start"]
    assert resume.enabled


def test_exhausted_credits_block_start_and_say_why() -> None:
    reason = acts(S.BACKLOG, None, limit=EXHAUSTED)["start"].reason
    assert reason == f"usage limit until {fmt_when(EXHAUSTED.until or 0, NOW)}; credits exhausted"


def test_yours_offers_start_wont_and_done_nothing() -> None:
    assert list(acts(S.YOURS, None, note=Note(repo=None))) == ["start", "wont", "done-manually"]  # T2092
    assert acts(S.DONE, run(stage="shipped", session_id="s", worktree="/w")) == {}


def test_queued_and_working_can_be_cancelled() -> None:
    assert list(acts(S.QUEUED, run())) == ["cancel", "done-manually", "send", "model"]
    assert acts(S.QUEUED, run(session_id="s"))["send"].reason == "the run is waiting to start"
    working = acts(S.WORKING, run(session_id="s", worktree="/w"), limit=LIMITED)
    assert working["cancel"].enabled
    assert working["send"].enabled
    assert working["cancel"].confirm


def test_send_without_a_session_is_disabled() -> None:
    send = acts(S.WORKING, run())["send"]
    assert (send.enabled, send.reason) == (False, "no Claude session yet")
    assert "copy-resume" not in acts(S.WORKING, run())


@pytest.mark.parametrize("run_state", [run(stage="failed", error="boom"), run(stage="spec_wait")])
def test_t2056_send_is_enabled_on_a_needs_you_card_with_no_session(run_state: RunState) -> None:
    got = acts(S.NEEDS_YOU, run_state)
    assert (got["send"].enabled, got["send"].reason) == (True, None)
    assert "copy-resume" not in got


def test_t2056_send_stays_disabled_without_a_session_while_queued_or_shipping() -> None:
    assert acts(S.QUEUED, run())["send"].reason == "no Claude session yet"
    assert acts(S.SHIPPING, run(stage="shipping"))["send"].reason == "no Claude session yet"


def test_copy_resume_value_and_missing_worktree() -> None:
    value = acts(S.WORKING, run(session_id="abc", worktree="/tmp/my wt"))["copy-resume"]
    assert value.enabled
    assert value.value == "cd '/tmp/my wt' && claude --resume abc"
    nowhere = acts(S.WORKING, run(session_id="abc"))["copy-resume"]
    assert (nowhere.enabled, nowhere.reason) == (False, "no worktree yet")


def test_shipping_cannot_be_cancelled() -> None:
    got = acts(S.SHIPPING, run(stage="shipping", session_id="s"))
    assert got["cancel"].reason == "shipping cannot be cancelled"
    assert got["send"].reason == "shipping is in progress"


def test_t1850_run_on_credits_action_is_gone() -> None:
    paused = run(stage="paused_limit", session_id="s")
    got = acts(S.PAUSED_LIMIT, paused, limit=LIMITED)
    assert "credits" not in got
    assert got["cancel"].enabled
    assert got["send"].reason.startswith("usage limit until")  # type: ignore[union-attr]


def test_spec_questions_actions() -> None:
    qs = [SpecQuestion("Q1", "a"), SpecQuestion("Q2", "b"), SpecQuestion("Q3", "c", answer="x")]
    got = acts(S.NEEDS_YOU, run(stage="spec_wait", spec_questions=qs))
    assert got["spec-answers"].enabled
    assert got["spec-ok"].reason == "2 question(s) still unanswered"


def test_spec_ok_actions() -> None:
    state = run(stage="spec_wait", spec_questions=[SpecQuestion("Q1", "a", answer="x")])
    got = acts(S.NEEDS_YOU, state)
    assert got["spec-ok"].enabled
    assert "spec-answers" not in got


def test_failed_run_offers_retry_and_handed_over_run_hands_back() -> None:
    failed = run(stage="failed", error="push refused")
    assert acts(S.NEEDS_YOU, failed)["start"].label == "Retry"
    assert acts(S.NEEDS_YOU, failed, missing="~/src/x")["start"].reason == "repo ~/src/x not found"
    handed = run(assignee="human", error="log in to X")
    assert acts(S.NEEDS_YOU, handed)["start"].label == "Hand back to Claude"
    stalled = run(stage="spec_wait", error="no progress")
    assert acts(S.NEEDS_YOU, stalled)["start"].label == "Retry"


def test_claude_question_offers_send_and_cancel_only() -> None:
    got = acts(S.NEEDS_YOU, run(last_tag="Q", session_id="s", worktree="/w"))
    assert list(got) == ["cancel", "wont", "done-manually", "send", "copy-resume", "model"]
    assert acts(S.NEEDS_YOU, run(last_tag="A", session_id="s"))["send"].enabled


def test_needs_you_without_a_run_offers_only_wont() -> None:
    assert list(acts(S.NEEDS_YOU, None)) == ["wont", "done-manually"]


def test_t2045_wont_rests_only_on_cards_no_turn_works_on() -> None:
    for status in (S.QUEUED, S.WORKING, S.SHIPPING, S.PAUSED_LIMIT, S.DONE):
        assert "wont" not in acts(status, run(worktree="/w")), status
    for status in (S.BACKLOG, S.CANCELLED):
        assert acts(status, None)["wont"].confirm


def test_cancelled_run_cannot_be_sent_to() -> None:
    assert "send" not in acts(S.CANCELLED, run(stage="cancelled", session_id="s"))


def test_lesson_approve_only_when_drafted() -> None:
    drafted = run(stage="gate", worktree="/w", lesson={"state": "drafted"})
    assert acts(S.SHIPPING, drafted)["lesson-approve"].enabled
    approved = run(stage="gate", worktree="/w", lesson={"state": "approved"})
    assert "lesson-approve" not in acts(S.SHIPPING, approved)


def test_to_dict_omits_unset_extras() -> None:
    assert Action("x", "X").to_dict() == {"id": "x", "label": "X", "enabled": True, "reason": None}
    assert Action("x", "X", confirm=True, value="v").to_dict()["value"] == "v"


def test_action_defaults_now_to_the_clock() -> None:
    got = actions(Note(), None, S.BACKLOG, LIMITED)
    assert got[0].reason is not None
    assert got[0].reason.startswith("usage limit until")


STATE_VARIANTS: list[dict[str, Any]] = [
    {},
    {"session_id": "s"},
    {"session_id": "s", "worktree": "/w"},
    {"error": "x"},
    {"last_tag": "Q"},
    {"lesson": {"state": "drafted"}},
    {"checks": {"passed": False}},
    {"spec_questions": [SpecQuestion("Q1", "a")]},
]


@pytest.mark.parametrize("stage", [*STAGES, None])
@pytest.mark.parametrize("assignee", ["claude", "human"])
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("limit", [NO_LIMIT, LIMITED, TAKEOVER, Limit(active=True, until=None)])
def test_every_combination_is_contract_valid_and_honest(
    stage: str | None, assignee: str, live: bool, limit: Limit
) -> None:
    for extra, repo in itertools.product(STATE_VARIANTS, ("demo", None)):
        note = Note(repo=repo)
        state = None if stage is None else run(stage=stage, assignee=assignee, **extra)
        status = compute(note, state, live, limit.until if limit.active else None)
        got = actions(note, state, status, limit, now=NOW)
        validate("common", [a.to_dict() for a in got], "actions")
        assert len({a.id for a in got}) == len(got)
        for a in got:
            assert a.enabled == (a.reason is None)
            if a.id == "start" and a.enabled:
                assert not limit.holds


def test_t2060_no_status_offers_ship_or_close_or_the_auto_ship_tick() -> None:
    for status in S:
        got = acts(status, run(stage="gate", worktree="/w", checks={"passed": True}, session_id="s"))
        assert not {"ship", "close"} & set(got), status
        assert all("option" not in a.to_dict() for a in got.values()), status


def test_t2064_done_manually_is_offered_on_every_card_that_is_not_done() -> None:
    for status in S:
        if status in (S.DONE, S.DONE_MANUALLY):
            assert "done-manually" not in acts(status, run(stage="shipped", session_id="s")), status
            continue
        offered = acts(status, run(worktree="/w"))["done-manually"]
        assert (offered.label, offered.confirm) == ("Done manually", True), status
    assert acts(S.BACKLOG, None)["done-manually"].enabled
    assert acts(S.DONE_MANUALLY, run(stage="done_manually", session_id="s", worktree="/w")) == {}


def test_t2064_done_manually_is_disabled_while_a_push_is_in_flight() -> None:
    shipping = acts(S.SHIPPING, run(stage="shipping", worktree="/w"))["done-manually"]
    assert (shipping.enabled, shipping.reason) == (False, "shipping cannot be stopped")
