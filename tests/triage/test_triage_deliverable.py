"""A research card closes its note only once a chosen action makes the note's own deliverable (T2091)."""

from pathlib import Path

from researchrig import ACTIONS, Rig, report, research_rig  # noqa: F401 - the `rig` fixture
from todoimpl.board.state import RunState, load
from todoimpl.prompts import PromptContext, build
from todoimpl.runner.stream import TurnResult
from todoimpl.triage import research

LOGO = "Make the personal logo: SVG master and PNG sizes"
ASK_LOGO = (
    "```ask\n"
    "choice c1: Candidates | Make note | *Skip | risk=reversible\n"
    "choice c2: The logo itself | Make note | *Skip | risk=reversible\n"
    "```\nA:"
)
WITH_LOGO = {
    "deliverable": LOGO,
    "actions": [
        {"id": "c1", "title": "Candidates", "repo": "kuhyx/utils", "body": "Draw six. Done: sheet."},
        {"id": "c2", "title": "Logo", "repo": "kuhyx/utils", "body": "Make it. Done: SVG.", "delivers": True},
    ],
}


def logo_run(rig: Rig, **picks: str) -> RunState:
    report(rig, WITH_LOGO)
    rig.replies.append(TurnResult(text=ASK_LOGO, tag="A", finished=True))
    rig.drive()
    rig.answer(**picks)
    rig.state = load(rig.dir)  # type: ignore[assignment]
    return rig.drive()


def test_t2091_the_note_stays_open_while_no_chosen_action_makes_its_deliverable(rig: Rig) -> None:
    """Kuhy's logo note was closed Done after research although no chosen action drew a logo."""
    state = logo_run(rig, c1="Make note", c2="Skip")
    assert rig.client.closed == []  # the note stays open
    assert state.stage == "failed"
    assert LOGO in str(state.error)  # and says what is missing
    assert "c1=abcdef01" in str(state.error)  # and what was made
    rig.answer(c1="Make note", c2="Make note")  # kuhy picks it after all, then Retry
    rig.state = state
    rig.state.stage = "implement"
    assert rig.drive().stage == "shipped"
    assert len(rig.client.added) == 2  # c1 is not made twice
    assert "c2=abcdef01" in rig.client.closed[0][1]


def test_t2091_a_chosen_delivering_action_closes_the_note(rig: Rig) -> None:
    state = logo_run(rig, c1="Skip", c2="Make note")
    assert state.stage == "shipped"
    assert len(rig.client.closed) == 1


def test_t2091_a_done_reply_does_not_close_a_note_with_a_deliverable(rig: Rig) -> None:
    report(rig, WITH_LOGO)
    rig.replies.append(TurnResult(text="Nothing to do.\nD:", tag="D", finished=True))
    state = rig.drive()
    assert (state.stage, rig.client.closed) == ("failed", [])
    assert LOGO in str(state.error)


def test_t2091_the_actions_and_the_deliverable_are_read_from_either_file_shape(rig: Rig) -> None:
    report(rig, WITH_LOGO)
    assert list(research._actions(rig.dir)) == ["c1", "c2"]
    assert research._deliverable(rig.dir) == LOGO
    report(rig, ACTIONS)  # the plain list: no deliverable declared
    assert research._deliverable(rig.dir) is None
    report(rig, {"deliverable": None, "actions": ACTIONS})
    assert research._deliverable(rig.dir) is None
    report(rig, {"deliverable": 3, "actions": "x"})
    assert (research._deliverable(rig.dir), research._actions(rig.dir)) == (None, {})


def test_t2091_the_prompt_asks_for_the_deliverable_and_the_delivering_action() -> None:
    text = build("research", PromptContext("t", "b", "", Path("/w"), Path("/r")))
    assert '"deliverable"' in text
    assert '"delivers": true' in text
