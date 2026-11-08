"""A Needs-you card names WHAT is needed; a generic line appears only when the run has no reply text."""

import pytest
from board_helpers import run
from todoimpl.board.needs import needs
from todoimpl.board.state import SpecQuestion

# Tail of card 340c295b-2's real last_reply: an empty `A:` line followed by an `N:` line holding the ask.
REPLY_340C295B = (
    "The plan is written to `/home/kuhy/.cache/todoImplementer/340c295b-2/plan.md` with Approach and C1-C9."
    " I edited nothing in the repo.\n\n"
    "The item is parked. `focus-project-v0.8.0` doesn't exist: the remote's newest tag is v0.7.1. Utils task"
    " `fda71ed1` has to build, merge and tag 0.8.0 first. Then rerun this item with the exact pin.\n\n"
    "Two things I found while planning:\n"
    "- `scripts/e2e_focus.py` already has an `f8`, so the split into F8 would collide.\n"
    "- `app/lib/l10n/` has only `app_en.arb`, so no Polish string is needed.\n\n"
    "A:\n"
    "N: Utils task `fda71ed1` must ship the `focus-project-v0.8.0` tag before this item can run."
)
ASK_340C295B = "Utils task `fda71ed1` must ship the `focus-project-v0.8.0` tag before this item can run."
GENERIC = (
    "see the feed",
    "answer it with Send to Claude",
    "Waiting for the phone",
    "without saying",
    "without a message",
)
NO_REPLY = "Claude ended without a reply: open Activity"
ROUND = (
    "Findings first.\n\n"
    "❓ **Q1** - **Pin the version**: Do I bump the pin?\n➡️ Yes.\n\n"
    "❓ **Q2** - **Old worker**: Keep the key optional?\n➡️ Yes.\n\n"
    "❓ **Q3** - **Docs**: Update the docs?\n➡️ No.\n\n"
)


def _answered(count: int) -> list[SpecQuestion]:
    return [SpecQuestion(f"Q{i}", "t", answer="a") for i in range(count)]


def test_t1835_empty_a_line_takes_the_n_line_not_the_generic_text() -> None:
    state = run(
        stage="plan", last_tag="A", spec_questions=_answered(13), extra={"last_reply": REPLY_340C295B}
    )
    got = needs(state)
    assert (got.kind, got.text) == ("claude_action", ASK_340C295B)


def test_t1835_empty_a_line_without_n_takes_the_paragraph_before_it_clipped() -> None:
    long = "Item 1 can only be checked partly. " * 12
    got = needs(run(last_tag="A", extra={"last_reply": f"Intro.\n\n{long}\n\nA:"}))
    assert got.text.startswith("Item 1 can only be checked partly.")
    assert len(got.text) <= 200
    assert got.text.endswith("…")


def test_t1835_empty_q_line_names_the_question_round() -> None:
    got = needs(run(last_tag="Q", extra={"last_reply": ROUND + "Q:"}))
    assert (got.kind, got.text) == ("claude_question", "3 questions: Pin the version")
    one = "❓ **Q1** - **Only one**: Really?\n➡️ Yes.\n\nQ:"
    assert needs(run(last_tag="Q", extra={"last_reply": one})).text == "1 question: Only one"


def test_t1835_question_round_counts_the_open_cards_when_the_tail_lost_the_cards() -> None:
    cards = [SpecQuestion("Q1", "Scope"), SpecQuestion("Q2", "Name")]
    got = needs(run(last_tag="Q", spec_questions=cards, extra={"last_reply": "Tail only.\n\nQ:"}))
    assert got.text == "2 questions: Scope"


def test_t1835_a_tag_line_ending_in_a_colon_carries_its_paragraph() -> None:
    reply = "A: need your answers on two points:\n- the crash\n- the flag\n\nNothing else."
    got = needs(run(last_tag="A", extra={"last_reply": reply}))
    assert got.text == "need your answers on two points: - the crash - the flag"


def test_t1835_a_reply_without_a_tag_gives_its_last_paragraph() -> None:
    got = needs(run(last_tag="A", extra={"last_reply": "First.\n\nPlease run `textgate approve`."}))
    assert got.text == "Please run `textgate approve`."


@pytest.mark.parametrize("tag", ["A", "Q"])
@pytest.mark.parametrize("extra", [{}, {"last_reply": ""}, {"last_reply": "  \n"}])
def test_t1835_no_reply_text_says_why_and_where_to_look(tag: str, extra: dict[str, str]) -> None:
    assert needs(run(last_tag=tag, extra=extra)).text == NO_REPLY


def test_t1835_spec_questions_name_the_first_open_title() -> None:
    cards = [SpecQuestion("Q1", "Scope"), SpecQuestion("Q2", "Name"), SpecQuestion("Q3", "Done", answer="x")]
    got = needs(run(stage="spec_wait", spec_questions=cards))
    assert (got.kind, got.text, got.effort) == ("spec_questions", "2 questions: Scope", 2)


def test_t1835_phone_wait_without_a_reply_names_the_criteria() -> None:
    wait = {"apk": "/a.apk", "criteria": ["C3", "C4"]}
    got = needs(run(last_tag="D", extra={"waiting_phone": wait}))
    assert got.kind == "claude_action"
    assert "C3, C4" in got.text
    assert "Pixel" in got.text


def test_t1835_handed_to_you_reads_the_reply_before_giving_up() -> None:
    got = needs(run(assignee="human", extra={"last_reply": "Log in to X.\n\nA: log in to X first."}))
    assert got.text == "log in to X first."
    assert needs(run(assignee="human")).text == NO_REPLY


def test_t1835_checks_failed_and_run_failed_name_what_failed() -> None:
    rows = [{"command": "make lint", "exit": 0, "tail": ""}, {"command": "make test", "exit": 2, "tail": "x"}]
    red = run(stage="failed", checks={"passed": False, "results": rows})
    assert needs(red).text == "Checks are still red after the fix attempts: make test (exit 2)"
    stopped = needs(run(stage="failed", checks={"passed": True}))
    assert stopped.text == "The run stopped in stage failed without an error message: open Activity"


def test_t1835_every_kind_avoids_the_generic_lines() -> None:
    wait = {"apk": "/a.apk", "criteria": ["C1"]}
    states = [
        run(last_tag="A", extra={"last_reply": "work\n\nA:"}),
        run(last_tag="Q", extra={"last_reply": "work\n\nQ:"}),
        run(last_tag="A"),
        run(last_tag="Q"),
        run(last_tag="D", extra={"waiting_phone": wait}),
        run(last_tag="A", extra={"waiting_phone": {**wait, "tried_attached": True}}),
        run(assignee="human"),
        run(stage="failed"),
        run(stage="failed", checks={"passed": False}),
        run(stage="spec_wait", spec_questions=_answered(2), last_tag="A"),
    ]
    for state in states:
        assert not any(g in needs(state).text for g in GENERIC), state


def test_t1835_untagged_question_cards_and_extra_blank_lines() -> None:
    got = needs(run(last_tag="Q", extra={"last_reply": ROUND}))
    assert got.text == "3 questions: Pin the version"
    spaced = needs(run(last_tag="A", extra={"last_reply": "One.\n\n\n\nTwo."}))
    assert spaced.text == "Two."
