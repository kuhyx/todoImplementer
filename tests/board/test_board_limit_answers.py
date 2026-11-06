"""Answers are only stored, so a usage-limit pause must not block spec-answers or spec-ok."""

from board_helpers import LIMITED, NOW, Note, ctx, run
from todoimpl.board.actions import actions
from todoimpl.board.card import build_card, current_line
from todoimpl.board.state import SpecQuestion
from todoimpl.board.status import Status
from todoimpl.board.types import fmt_when


def _by_id(state_questions: list[SpecQuestion]) -> dict[str, object]:
    state = run(stage="spec_wait", spec_questions=state_questions)
    return {a.id: a for a in actions(Note(), state, Status.NEEDS_YOU, LIMITED, now=NOW)}


def test_t1800_spec_answers_stay_enabled_during_a_usage_limit() -> None:
    got = _by_id([SpecQuestion("Q1", "a"), SpecQuestion("Q2", "b", answer="x")])
    assert got["spec-answers"].enabled  # type: ignore[attr-defined]
    assert got["spec-answers"].reason is None  # type: ignore[attr-defined]


def test_t1800_spec_ok_stays_enabled_during_a_usage_limit() -> None:
    got = _by_id([SpecQuestion("Q1", "a", answer="x")])
    assert got["spec-ok"].enabled  # type: ignore[attr-defined]


def test_t1800_answered_run_waits_in_the_limit_and_says_so() -> None:
    state = run(stage="spec", spec_questions=[SpecQuestion("Q1", "a", answer="x")])
    line = current_line(Status.PAUSED_LIMIT, state, LIMITED.until, NOW)
    assert line == f"answers saved; Claude continues after {fmt_when(LIMITED.until or 0, NOW)}"
    card = build_card(Note(), state, ctx(limit=LIMITED))
    assert card["status"] == "paused_limit"
    assert card["current"] == line


def test_t1800_answered_run_with_unknown_end_says_when_the_limit_passes() -> None:
    state = run(stage="spec", spec_questions=[SpecQuestion("Q1", "a", answer="x")])
    assert (
        current_line(Status.PAUSED_LIMIT, state, None, NOW)
        == "answers saved; Claude continues when the limit passes"
    )
