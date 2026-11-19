"""A note that asks to make something is never `research`, whatever it says about research (T2090)."""

from collections.abc import Callable

from conftest import Triage
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.triage import classify, label

Make = Callable[..., Triage]
REPOS = ["kuhyx/utils", "kuhyx/personal-website"]
TITLE = 'Logo for "me" my personal logo'
BODY = (
    "i was thinking\nK U\n H Y \nin bold letters\nresrarch idea of personal logos, is it a thign? "
    "if yes how do you create one? make it follow all rules of good logos"
)
RESEARCH = {"label": "research", "reason": "Asks to research whether personal monogram logos are a thing"}
NEW = {"label": "new_repo", "name": "kuhy-logo", "reason": "asks for a logo"}


def test_t2090_the_prompt_says_a_note_that_makes_something_is_never_research() -> None:
    prompt = classify.build_prompt(TITLE, BODY, REPOS)
    assert "never research" in prompt
    assert "even when" in prompt  # "even when it says research how"
    assert "personal logo" in prompt  # the note's own text rides along


def test_t2090_research_needs_a_url_to_read() -> None:
    assert not classify.has_url(TITLE, BODY)
    assert classify.has_url("reading", "see https://paulgraham.com/google.html\nand more")
    assert classify.has_url("http://x.example", "")


def test_t2090_a_logo_note_labelled_research_is_asked_again_and_takes_the_new_label(
    rig: Rig, triage: Make
) -> None:
    card = rig.note(TITLE, BODY, repo=None)
    run = triage(RESEARCH, NEW)
    assert run.service.tick() == 1
    assert len(run.prompts) == 2
    assert "no URL" in run.prompts[1]  # the second ask names the mistake
    assert label.label_of(run_dir(rig.root, card)) == "new_repo"


def test_t2090_a_second_research_answer_without_a_url_falls_back_to_manual(rig: Rig, triage: Make) -> None:
    card = rig.note(TITLE, BODY, repo=None)
    run = triage(RESEARCH, RESEARCH)
    assert run.service.tick() == 1
    stored = label.load(run_dir(rig.root, card))
    assert stored is not None
    assert stored["label"] == "manual"
    assert "no URL" in stored["reason"]


def test_t2090_a_note_with_a_url_keeps_its_research_label_after_one_call(rig: Rig, triage: Make) -> None:
    card = rig.note("https://paulgraham.com/google.html", repo=None)
    run = triage(RESEARCH)
    assert run.service.tick() == 1
    assert len(run.prompts) == 1
    assert label.label_of(run_dir(rig.root, card)) == "research"
