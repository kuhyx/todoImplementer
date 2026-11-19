"""Research cards: a session with no repo reports and offers choices; the server makes the notes picked."""

from researchrig import ACTIONS, ASK, Rig, report, research_rig  # noqa: F401 - the `rig` fixture
from todoimpl.board.state import RunState, load
from todoimpl.prompts import PromptContext, build
from todoimpl.runner import stages, tiering
from todoimpl.runner.pipeline import Driver
from todoimpl.runner.stream import TurnResult
from todoimpl.todo_mcp.items import Item
from todoimpl.triage import research
from todoimpl.triage.label import MANUAL, RESEARCH, Verdict, save
from todoimpl.triage.research import ResearchDriver
from todoimpl.umbrella.driver import driver_for


def test_t2073_a_note_of_urls_is_researched_with_no_repo_and_rests_on_its_choices(rig: Rig) -> None:
    report(rig)
    rig.replies.append(TurnResult(text=f"Done reading.\n{ASK}", tag="A", finished=True))
    state = rig.drive()
    assert (state.stage, state.last_tag, rig.turns) == ("implement", "A", 1)  # spec and plan skipped
    assert state.worktree == str(rig.dir / "research")  # no git worktree: a scratch dir
    assert (state.extra["research"], state.extra["tier"]) == (True, "cheap")
    assert state.live_check == {"report_md": "Key ideas: many.", "shots": []}  # the drawer shows the report
    assert rig.client.added == []
    assert rig.client.closed == []


def test_t2073_picked_actions_become_notes_and_the_research_note_is_closed(rig: Rig) -> None:
    report(rig)
    rig.replies.append(TurnResult(text=ASK, tag="A", finished=True))
    rig.drive()
    rig.answer(c1="Make note", c2="Make note")
    rig.state = load(rig.dir)  # type: ignore[assignment]
    state = rig.drive()
    assert rig.turns == 1  # no second turn: the server makes the notes
    assert rig.client.added == [("kuhyx/kuhylog", "Digest in kuhylog", "Add it. Done: it shows.")]
    assert rig.umbrellas == [
        "New reader app\n\nBuild it. Done: it runs."
    ]  # no repo: the todo CLI, triage routes it
    assert state.stage == "shipped"
    card, evidence = rig.client.closed[0]
    assert card == "f206969c-0"
    assert "c1=abcdef01" in evidence
    assert "c2=99999999" in evidence


def test_t2073_a_skipped_action_makes_no_note_and_a_failed_one_is_made_once_on_retry(rig: Rig) -> None:
    report(rig)
    rig.replies.append(TurnResult(text=ASK, tag="A", finished=True))
    rig.drive()
    rig.answer(c1="Make note", c2="Skip")
    rig.state = load(rig.dir)  # type: ignore[assignment]
    rig.client.fail = True
    failed = rig.drive()
    assert failed.stage == "failed"
    assert "research note not made: c1: todo app down" in str(failed.error)
    rig.client.fail = False
    rig.state = failed
    rig.state.stage = "implement"
    assert rig.drive().stage == "shipped"
    assert len(rig.client.added) == 1
    assert rig.umbrellas == []
    assert "skipped 1" in rig.client.closed[0][1]


def test_t2073_a_reply_without_choices_closes_on_done_or_rests_on_a_question(rig: Rig) -> None:
    rig.replies.append(TurnResult(text="Nothing worth doing.\nD:", tag="D", finished=True))
    done = rig.drive()
    assert done.stage == "shipped"
    assert "notes made none; skipped 0" in rig.client.closed[0][1]
    rig.client.closed.clear()
    rig.state = RunState("f206969c-0", "spec", repo=None)
    rig.replies.append(TurnResult(text="Which of the two?\nQ:", tag="Q", finished=True))
    asked = rig.drive()
    assert (asked.stage, asked.last_tag, rig.client.closed) == ("implement", None, [])


def test_t2073_an_unwritten_report_falls_back_to_the_reply(rig: Rig) -> None:
    rig.replies.append(TurnResult(text=ASK, tag="D", finished=True))
    state = rig.drive()
    assert (state.live_check or {})["report_md"] == ASK
    assert state.last_tag == "A"  # the choices are the ask whatever tag the session ended on
    assert rig.turns == 1  # research.json is missing: the answers could not make notes, so no finish


def test_t2073_malformed_actions_are_dropped(rig: Rig) -> None:
    bad: list[object] = [
        "text",
        {"id": "c1", "title": "t", "body": " "},
        {"id": "c2", "title": "t", "body": "b", "repo": "not a repo"},
        {"id": "c3", "title": "t", "body": "b", "repo": 3},
        {"id": "c4", "title": "ok", "body": "b", "repo": "kuhyx/x"},
    ]
    report(rig, bad)
    assert list(research._actions(rig.dir)) == ["c4"]
    report(rig, {"not": "a list"})
    assert research._actions(rig.dir) == {}
    (rig.dir / "research.json").write_text("{broken")
    assert research._actions(rig.dir) == {}
    (rig.dir / research.DONE_FILE).write_text("[1]")
    assert research._made(rig.dir) == {}


def test_t2073_only_a_repo_less_research_label_gets_the_research_driver(rig: Rig) -> None:
    ctx = rig.ctx()
    assert type(driver_for(ctx, rig.state, rig.item)) is Driver  # no label yet
    save(rig.dir, Verdict(MANUAL), "d", 1.0)
    assert type(driver_for(ctx, rig.state, rig.item)) is Driver
    save(rig.dir, Verdict(RESEARCH), "d", 1.0)
    assert type(driver_for(ctx, rig.state, rig.item)) is ResearchDriver
    with_repo = Item("f206969c", 0, "t", "", "kuhyx/x", "todo", None, "kuhy")
    assert type(driver_for(ctx, rig.state, with_repo)) is Driver


def test_t2073_the_research_turn_runs_on_sonnet_and_the_prompt_names_the_files(rig: Rig) -> None:
    rig.state.extra["research"] = True
    turn = tiering.plan_turn(Driver(rig.ctx(), rig.state, rig.item), "implement")
    assert (turn.model, turn.effort, turn.note) == ("sonnet", "medium", "")
    ctx = PromptContext("t", "https://x.example/a", "", rig.dir / "research", rig.dir, notes=("also this",))
    text = build("research", ctx)
    assert text.startswith("override\n")
    assert f"{rig.dir}/research.md" in text
    assert f"{rig.dir}/research.json" in text
    assert "free-llm" in text
    assert "kuhy's note: also this" in text
    assert stages.HANDLERS["implement"] is stages._implement
