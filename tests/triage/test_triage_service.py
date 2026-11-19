"""Triage of repo-less notes: the label, the card it gives, and the one action that needs no click."""

import threading
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Triage
from contract_lib import validate
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.repotask.ids import repo_card_id
from todoimpl.todo_mcp.model import TodoError
from todoimpl.triage import label, service
from todoimpl.triage.classify import ClassifyError

Make = Callable[..., Triage]
NEW = {"label": "new_repo", "name": "pacman-gui", "reason": "asks for a new app"}


def actions(card: dict[str, object]) -> dict[str, bool]:
    return {a["id"]: a["enabled"] for a in card["actions"]}  # type: ignore[attr-defined]


def test_t2070_a_note_that_asks_for_a_new_app_is_labelled_and_startable(rig: Rig, triage: Make) -> None:
    card = rig.note("gui for pacman and yay", repo=None)
    assert rig.card(card)["status"] == "yours"  # before triage: kuhy's
    assert triage(NEW).service.tick() == 1
    rig.backend.cache.refresh()
    shown = rig.card(card)
    validate("board", rig.backend.board())
    assert (shown["triage"], shown["status"], shown["assignee"]) == ("new_repo", "backlog", "claude")
    assert actions(shown)["start"] is True


def test_t2070_a_manual_note_stays_yours_with_start_and_the_two_hand_endings(rig: Rig, triage: Make) -> None:
    card = rig.note("wysłać jpk", repo=None)
    triage({"label": "manual", "reason": "an errand"}).service.tick()
    rig.backend.cache.refresh()
    shown = rig.card(card)
    assert (shown["triage"], shown["status"]) == ("manual", "yours")
    assert [a["id"] for a in shown["actions"]] == ["start", "wont", "done-manually"]  # T2092


def test_t2070_an_existing_repo_label_sets_the_repo_and_the_card_joins_that_repos(
    rig: Rig, triage: Make
) -> None:
    rig.note("utils todos", "## a\nx", repo="kuhyx/utils")
    card = rig.note("add a flag to the lock script", repo=None)
    verdict = {"label": "existing_repo", "repo": "KUHYX/utils", "reason": "a utils script"}
    assert triage(verdict).service.tick() == 1
    ids = {c["id"] for c in rig.backend.board()["tasks"]}
    assert card not in ids  # the note has a repo now: its sections are parts of the repo's one card
    assert repo_card_id("kuhyx/utils") in ids
    parts = rig.card(repo_card_id("kuhyx/utils"))["parts"]
    assert len(parts) == 2


def test_t2070_an_unknown_repo_or_a_bad_name_falls_back_to_manual(rig: Rig, triage: Make) -> None:
    rig.note("one", repo=None)
    rig.note("two", repo=None)
    both = triage(
        {"label": "existing_repo", "repo": "kuhyx/nope"}, {"label": "new_repo", "name": "Not A Name!"}
    )
    assert both.service.tick() == 2
    rig.backend.cache.refresh()
    assert {c["triage"] for c in rig.backend.board()["tasks"]} == {"manual"}


def test_t2070_a_repo_the_todo_app_refuses_is_kept_as_an_error_on_the_label(
    rig: Rig, triage: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = rig.note("x for utils", repo=None)
    run = triage({"label": "existing_repo", "repo": "kuhyx/utils"})

    def refuse(*_a: object, **_k: object) -> None:
        raise TodoError("repo: refused")

    monkeypatch.setattr(run.service.client, "update_task", refuse)
    run.service.tick()
    found = label.load(run_dir(rig.root, card))
    assert found is not None
    assert found["error"] == "repo: refused"


def test_t2070_a_note_is_classified_once_and_again_when_its_text_changes(rig: Rig, triage: Make) -> None:
    note = rig.fake.seed(None, "an idea")
    rig.backend.cache.refresh()
    run = triage({"label": "manual"}, {"label": "manual"})
    assert (run.service.tick(), run.service.tick()) == (1, 0)
    assert len(run.prompts) == 1
    rig.fake.store.notes[note].text = "an idea, now longer"
    rig.backend.cache.refresh()
    assert run.service.tick() == 1
    assert "now longer" in run.prompts[1]
    assert "kuhyx/utils" in run.prompts[0]  # the repo list rides along


def test_t2070_a_failed_call_leaves_the_note_untriaged_and_waits_before_retrying(
    rig: Rig, triage: Make
) -> None:
    card = rig.note("https://x.example/idea", repo=None)
    run = triage(ClassifyError("claude down"), {"label": "research"})
    assert run.service.tick() == 0
    assert run.service.tick() == 0  # still inside the retry wait
    assert len(run.prompts) == 1
    assert label.label_of(run_dir(rig.root, card)) is None
    run.now += service.RETRY_S
    assert run.service.tick() == 1
    assert label.label_of(run_dir(rig.root, card)) == "research"


def test_t2070_only_open_single_note_cards_without_a_run_are_triaged(rig: Rig, triage: Make) -> None:
    rig.note("MANUAL WORK REQUIRED: call", repo=None)
    rig.note("umbrella", "Umbrella: per-repo\n## kuhyx/a (abcd1234)\nx", repo=None)
    rig.fake.seed(None, "sections", "## a\nx\n\n## b\ny")
    rig.fake.seed(None, "finished", status="done")
    started = rig.note("already started", repo=None)
    rig.run(started, "implement")
    rig.backend.cache.refresh()
    assert triage().service.due() == []


def test_t2070_the_loop_survives_a_failing_tick(
    rig: Rig, triage: Make, monkeypatch: pytest.MonkeyPatch
) -> None:
    run, ticks, done = triage(), [], threading.Event()

    def fake_tick() -> int:
        ticks.append(1)
        if len(ticks) == 1:
            raise RuntimeError("boom")
        done.set()
        return 0

    monkeypatch.setattr(service, "TICK", 0.01)
    monkeypatch.setattr(run.service, "tick", fake_tick)
    run.service.watch()
    assert done.wait(5)


def test_t2070_a_note_of_urls_is_labelled_research_and_startable(rig: Rig, triage: Make) -> None:
    card = rig.note("https://paulgraham.com/google.html", repo=None)
    triage({"label": "research", "reason": "an article"}).service.tick()
    rig.backend.cache.refresh()
    shown = rig.card(card)
    assert (shown["triage"], shown["status"], actions(shown)["start"]) == ("research", "backlog", True)
    rig.backend.start(card)  # the plain scheduler path: the research driver is picked by the label
    assert ("start", card, None) in rig.scheduler.calls


def test_t2070_adding_facts_to_a_missing_record_is_a_no_op(tmp_path: Path) -> None:
    label.update(tmp_path, error="x")
    assert label.load(tmp_path) is None
