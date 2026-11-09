# ruff: noqa: FBT003, PLR0917
"""compute/column/needs: the single status, over every (stage, assignee, live, limit) combination."""

import itertools

import pytest
from board_helpers import STAGES, Note, run
from todoimpl.board.needs import needs
from todoimpl.board.state import SpecQuestion
from todoimpl.board.status import Column, Status, column, compute

W, Q, P, N, R, D, Y, S, C = (
    Status.WORKING,
    Status.QUEUED,
    Status.PAUSED_LIMIT,
    Status.NEEDS_YOU,
    Status.READY_TO_SHIP,
    Status.DONE,
    Status.YOURS,
    Status.SHIPPING,
    Status.CANCELLED,
)
# (live, limit) order: (no, no), (no, yes), (yes, no), (yes, yes)
WORK = (Q, P, W, W)
CLAUDE: dict[str, tuple[Status, ...]] = {
    "spec": WORK,
    "plan": WORK,
    "implement": WORK,
    "live_check": WORK,
    "checks": WORK,
    "spec_wait": (N,) * 4,
    "gate": (R,) * 4,
    "shipping": (S,) * 4,
    "shipped": (D,) * 4,
    "failed": (N,) * 4,
    "paused_limit": (P,) * 4,
    "paused_retry": (W, P, W, W),
    "cancelled": (C,) * 4,
}
HUMAN: dict[str, tuple[Status, ...]] = dict.fromkeys(STAGES, (Y,) * 4)
HUMAN["shipped"] = (D,) * 4
HUMAN["cancelled"] = (C,) * 4
COMBOS = list(itertools.product((False, True), repeat=2))


def test_table_covers_every_stage() -> None:
    assert set(CLAUDE) == set(STAGES) == set(HUMAN)


@pytest.mark.parametrize(("assignee", "table"), [("claude", CLAUDE), ("human", HUMAN)])
@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize(("live", "limited"), COMBOS)
def test_every_stage_assignee_live_limit(
    assignee: str, table: dict[str, tuple[Status, ...]], stage: str, live: bool, limited: bool
) -> None:
    expected = table[stage][COMBOS.index((live, limited))]
    got = compute(Note(), run(stage=stage, assignee=assignee), live, 123.0 if limited else None)
    assert got == expected


def test_closed_note_is_done_even_with_a_failed_run() -> None:
    assert compute(Note(status="done"), run(stage="failed", error="x"), False, None) == Status.DONE
    assert compute(Note(status="abandoned"), None, False, None) == Status.CANCELLED


def test_t1815_cancelled_or_abandoned_leaves_the_backlog_for_done() -> None:
    assert compute(Note(status="abandoned"), run(stage="failed", error="x"), False, None) == Status.CANCELLED
    assert compute(Note(), run(stage="cancelled"), False, None) == Status.CANCELLED
    assert column(Status.CANCELLED).value == "done"


def test_no_run_is_backlog_or_yours() -> None:
    assert compute(Note(), None, False, None) == Status.BACKLOG
    assert compute(Note(repo=None), None, False, 99.0) == Status.YOURS


def test_error_or_unread_tag_needs_you_unless_live_tag() -> None:
    assert compute(Note(), run(error="boom"), True, None) == Status.NEEDS_YOU
    assert compute(Note(), run(last_tag="Q"), False, None) == Status.NEEDS_YOU
    assert compute(Note(), run(last_tag="A"), False, 5.0) == Status.NEEDS_YOU
    assert compute(Note(), run(last_tag="Q"), True, None) == Status.WORKING
    assert compute(Note(), run(last_tag="D"), False, None) == Status.QUEUED


def test_human_with_a_stated_need_is_needs_you() -> None:
    assert compute(Note(), run(assignee="human", error="log in to X"), False, None) == Status.NEEDS_YOU


def test_a_limit_that_holds_pauses_a_queued_run_and_none_leaves_it_queued() -> None:
    assert compute(Note(), run(), False, 5.0) == Status.PAUSED_LIMIT
    assert compute(Note(), run(), False, None) == Status.QUEUED
    assert compute(Note(), run(stage="paused_limit"), False, None) == Status.PAUSED_LIMIT


def test_manual_work_note_is_yours_with_or_without_a_repo_and_a_run() -> None:
    manual = Note(title="MANUAL WORK REQUIRED: rotate key")
    assert compute(manual, None, False, None) == Status.YOURS
    assert compute(manual, run(), False, None) == Status.YOURS
    assert compute(Note(title="manual work required: x"), None, False, None) == Status.BACKLOG


def test_gate_wins_over_limit_because_shipping_needs_no_claude() -> None:
    assert compute(Note(), run(stage="gate"), False, 5.0) == Status.READY_TO_SHIP


@pytest.mark.parametrize("stage", STAGES)
@pytest.mark.parametrize("assignee", ["human", "claude"])
@pytest.mark.parametrize("live", [False, True])
@pytest.mark.parametrize("limit_until", [None, 9.0])
@pytest.mark.parametrize("error", [None, "why"])
@pytest.mark.parametrize("tag", [None, "Q", "A", "R", "D"])
def test_every_combination_has_exactly_one_status_and_a_consistent_column(
    stage: str, assignee: str, live: bool, limit_until: float | None, error: str | None, tag: str | None
) -> None:
    state = run(stage=stage, assignee=assignee, error=error, last_tag=tag)
    status = compute(Note(), state, live, limit_until)
    assert isinstance(status, Status)
    assert column(status) in Column
    if status == Status.NEEDS_YOU:
        assert needs(state).text


def test_columns() -> None:
    assert {s: column(s).value for s in Status} == {
        Status.BACKLOG: "backlog",
        Status.YOURS: "backlog",
        Status.CANCELLED: "done",
        Status.QUEUED: "running",
        Status.WORKING: "running",
        Status.PAUSED_LIMIT: "running",
        Status.SHIPPING: "running",
        Status.NEEDS_YOU: "needs_you",
        Status.READY_TO_SHIP: "ready",
        Status.DONE: "done",
    }


def test_needs_kinds() -> None:
    asked = [SpecQuestion("Q1", "Scope"), SpecQuestion("Q2", "Name", answer="x")]
    answered = [SpecQuestion("Q1", "Scope", answer="y")]
    cases = [
        (run(assignee="human", error="log in to X"), "handed_to_you", "log in to X"),
        (run(assignee="human"), "handed_to_you", None),
        (run(stage="spec_wait", spec_questions=asked), "spec_questions", "1 question: Scope"),
        (run(stage="spec_wait", spec_questions=answered), "spec_ok", None),
        (run(stage="spec_wait", last_tag="Q"), "claude_question", None),
        (run(stage="spec_wait", last_tag="A"), "claude_action", None),
        (run(stage="spec_wait", error="odd"), "run_failed", "odd"),
        (run(stage="failed", checks={"passed": False}), "checks_failed", None),
        (run(stage="failed", checks={"passed": True}, last_tag="Q"), "run_failed", None),
        (run(stage="failed", checks={"ran_at": 1}), "run_failed", None),
        (run(stage="failed", error="push refused"), "run_failed", "push refused"),
        (run(last_tag="Q"), "claude_question", None),
        (run(last_tag="A", error="Install the CA cert"), "claude_action", "Install the CA cert"),
        (run(error="crashed"), "run_failed", "crashed"),
    ]
    for state, kind, text in cases:
        got = needs(state)
        assert got.kind == kind, state
        assert got.text
        if text is not None:
            assert got.text == text
    assert needs(run(error="e")).to_dict() == {
        "kind": "run_failed",
        "text": "e",
        "category": "action",
        "effort": 4,
    }


@pytest.mark.parametrize("tag", ["Q", "A", "R", "D"])
def test_t1229_a_paused_retry_run_is_never_needs_you(tag: str) -> None:
    waiting = run(stage="paused_retry", last_tag=tag)
    assert compute(Note(), waiting, False, None) == Status.WORKING
    assert compute(Note(), waiting, False, 5.0) != Status.NEEDS_YOU
