"""Needs text, category and effort; Needs-you sort; the partial object on a card."""

from typing import Any

import pytest
from board_helpers import NOW, Note, ctx, run
from contract_lib import validate
from todoimpl.board import board
from todoimpl.board.card import build_card, partial_of
from todoimpl.board.needs import needs
from todoimpl.board.state import RunState, SpecQuestion
from todoimpl.runner.stream import last_tag_line


def test_t1100_claude_action_shows_the_last_a_line() -> None:
    reply = (
        "Lots of work.\n\nA: attach the phone with ADB authorized, then re-run the implementation stage.\n"
    )
    got = needs(run(last_tag="A", extra={"last_reply": reply}))
    assert got.text == "attach the phone with ADB authorized, then re-run the implementation stage."
    assert (got.kind, got.category, got.effort) == ("claude_action", "action", 3)
    asked = needs(run(last_tag="Q", extra={"last_reply": "**Q:** which name?"}))
    assert (asked.text, asked.category, asked.effort) == ("which name?", "questions", 1)


def test_t1100_generic_text_only_without_a_matching_reply() -> None:
    for extra in ({}, {"last_reply": "no tag here"}, {"last_reply": "D: done"}, {"last_reply": "A:"}):
        assert "see the feed" in needs(run(last_tag="A", extra=extra)).text


def test_last_tag_line_forms() -> None:
    assert last_tag_line("nothing") is None
    assert last_tag_line("R: x\nNEEDS ACTION: do it") == ("A", "do it")
    assert last_tag_line("Q: last line without newline") == ("Q", "last line without newline")


@pytest.mark.parametrize("count", [1, 3, 20])
def test_t1804_question_effort_is_the_open_question_count(count: int) -> None:
    cards = [SpecQuestion(f"Q{i}", "t") for i in range(count)]
    state = run(stage="spec_wait", spec_questions=cards)
    got = needs(state)
    assert (got.category, got.effort) == ("questions", count)
    validate("common", build_card(Note(), state, ctx()), "task_card")


def test_t1101_other_kinds_category_and_effort() -> None:
    done = [SpecQuestion("Q1", "t", answer="a")]
    cases = [
        (run(stage="spec_wait", spec_questions=done), ("action", 1)),
        (run(assignee="human"), ("action", 4)),
        (run(stage="failed", checks={"passed": False}), ("action", 4)),
        (run(stage="failed", error="x", extra={"failed_stage": "live_check"}), ("criteria", 2)),
        (run(stage="failed", error="x", extra={"auto_heal": True}), ("auto", 1)),
        (run(stage="failed", error="x"), ("action", 4)),
        (run(error="x", extra={"waiting_phone": True}), ("phone", 1)),
    ]
    for state, expected in cases:
        got = needs(state)
        assert (got.category, got.effort) == expected, state


def test_t1101_needs_you_sorted_by_effort_then_age() -> None:
    def ask(card: str, **fields: Any) -> tuple[Note, RunState]:
        return Note(id=card), run(task_id=card, **fields)

    pairs = [
        ask("aaaaaaaa-0", stage="failed", error="x", updated=NOW),
        ask("bbbbbbbb-0", stage="failed", error="x", extra={"auto_heal": True}, updated=NOW),
        ask("cccccccc-0", stage="failed", error="x", updated=NOW - 100),
        ask("dddddddd-0", stage="failed", error="x", extra={"failed_stage": "live_check"}, updated=NOW),
    ]
    out = board.build_board([n for n, _ in pairs], {r.task_id: r for _, r in pairs}, ctx(), "b")
    ids = [card["id"] for card in out["tasks"]]
    assert ids == ["bbbbbbbb-0", "dddddddd-0", "cccccccc-0", "aaaaaaaa-0"]


def test_t1811_questions_come_first_however_many_then_criteria() -> None:
    questions = [SpecQuestion(id=f"q{i}", title=f"Q{i}") for i in range(9)]
    pairs = [
        (
            Note(id="aaaaaaaa-0"),
            run(
                task_id="aaaaaaaa-0",
                stage="failed",
                error="x",
                extra={"failed_stage": "live_check"},
                updated=NOW,
            ),
        ),
        (
            Note(id="bbbbbbbb-0"),
            run(task_id="bbbbbbbb-0", stage="spec_wait", spec_questions=questions, updated=NOW),
        ),
    ]
    out = board.build_board([n for n, _ in pairs], {r.task_id: r for _, r in pairs}, ctx(), "b")
    assert [card["id"] for card in out["tasks"]] == ["bbbbbbbb-0", "aaaaaaaa-0"]


def test_t1107_card_partial_object_validates() -> None:
    state = run(
        stage="gate",
        extra={"partial": {"done": ["C1"], "open": ["C2"], "deferred": ["C3"]}, "followup_id": "abcd1234"},
    )
    card = build_card(Note(), state, ctx())
    validate("common", card, "task_card")
    assert card["partial"] == {"done": ["C1"], "open": ["C2"], "deferred": ["C3"], "followup_id": "abcd1234"}
    assert partial_of(None) is None
    assert partial_of(run()) is None
