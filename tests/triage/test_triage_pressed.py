"""Start on a repo-less note nothing can start: triage it as code work, then route it (kuhy, 2026-11-19)."""

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest
from conftest import Triage
from servicefakes import Rig
from todoimpl.board.state import load, run_dir
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.scheduler import RunnerError
from todoimpl.triage import label
from todoimpl.triage.classify import PRESSED

Make = Callable[..., Triage]
TITLE, BODY = "Logo for me", "K U / H Y in bold\nDone: logo drawn"


def manual(rig: Rig, title: str = TITLE, body: str = BODY, found: str | None = "manual") -> str:
    """Seed a repo-less note triage called not code (`found`) or never saw (None), on the real fetch path."""
    card = rig.note(title, body, repo=None)
    if found is not None:
        label.save(run_dir(rig.root, card), label.Verdict(found), label.digest(title, body), 1.0)
        rig.backend.cache.refresh()
    return card


def start_ids(rig: Rig) -> list[str]:
    return [c[1] for c in rig.scheduler.calls if c[0] == "start"]


@pytest.mark.parametrize("found", ["manual", None])
def test_t2092_a_yours_card_offers_start_whatever_its_label(rig: Rig, found: str | None) -> None:
    """The action list said Won't do and Done manually only, so kuhy could not start a note triage misread."""
    card = manual(rig, found=found)
    shown = rig.card(card)
    assert shown["status"] == "yours"
    assert next((a["id"], a["enabled"]) for a in shown["actions"]) == ("start", True)


def test_t2092_a_manual_work_title_still_has_no_start(rig: Rig) -> None:
    shown = rig.card(manual(rig, title="MANUAL WORK REQUIRED: sign the form", found=None))
    assert next((a["id"], a["enabled"]) for a in shown["actions"]) == ("start", False)


def test_t2092_start_triages_again_with_the_hint_and_the_note_joins_the_repo_card(
    rig: Rig, triage: Make
) -> None:
    card = manual(rig)
    run = triage({"label": "existing_repo", "repo": "kuhyx/utils", "reason": "logo set lives there"})
    rig.backend.start(card)  # the real click path, a job runs inline in the rig
    assert run.prompts[0].endswith(PRESSED)
    assert next(n for n in rig.fake.store.notes.values() if n.text.startswith(TITLE)).repo == "kuhyx/utils"
    assert start_ids(rig) == [repo_card_id("kuhyx/utils")]
    assert card not in {c["id"] for c in rig.backend.board()["tasks"]}
    assert (label.label_of(run_dir(rig.root, card)), run.service._busy) == ("existing_repo", set())


def test_t2092_a_repo_card_at_work_takes_the_note_as_a_part_without_an_error(rig: Rig, triage: Make) -> None:
    card = manual(rig)
    rig.scheduler.failure = RunnerError("busy", "conflict")
    triage({"label": "existing_repo", "repo": "kuhyx/utils", "reason": "x"})
    rig.backend.start(card)
    assert load(run_dir(rig.root, card)) is None


def test_t2092_start_on_a_new_app_note_makes_the_repo(rig: Rig, triage: Make) -> None:
    card = manual(rig, found=None)
    run = triage({"label": "new_repo", "name": "me-logo", "reason": "a new thing"})
    rig.backend.start(card)
    assert [c["name"] for c in run.created] == ["me-logo"]
    assert start_ids(rig) == [repo_card_id("kuhyx/me-logo")]


def test_t2092_start_on_an_all_repos_note_makes_the_umbrella_and_starts_it(
    rig: Rig, triage: Make, tmp_path: Path
) -> None:
    path = tmp_path / "src" / "utils"
    (path / ".github").mkdir(parents=True)
    (path / ".github" / "ci.yml").write_text("freshness\n")
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    card = manual(rig)
    triage({"label": "all_repos", "token": "freshness", "path": ".github", "reason": "every repo"})
    rig.backend.start(card)
    assert start_ids(rig) == [card]
    assert rig.card(card)["umbrella"]["total"] == 1


def test_t2092_an_all_repos_note_matching_no_repo_rests_failed_with_the_reason(
    rig: Rig, triage: Make, tmp_path: Path
) -> None:
    card = manual(rig)
    triage({"label": "all_repos", "token": "nothing-matches", "reason": "x"})
    rig.backend.start(card)
    state = load(run_dir(rig.root, card))
    assert state is not None
    assert (state.stage, state.error) == ("failed", "start: no repo matches")
    assert start_ids(rig) == []


def test_t2092_a_research_answer_starts_the_research_run(rig: Rig, triage: Make) -> None:
    card = manual(rig, body="https://x.example/reading")
    triage({"label": "research", "reason": "links"})
    rig.backend.start(card)
    assert start_ids(rig) == [card]


def test_t2092_a_note_still_not_code_rests_failed_and_retry_asks_again(rig: Rig, triage: Make) -> None:
    card = manual(rig)
    run = triage({"label": "manual", "reason": "an errand"}, {"label": "new_repo", "name": "me-logo"})
    rig.backend.start(card)
    state = load(run_dir(rig.root, card))
    assert state is not None
    assert (state.stage, state.error) == ("failed", "start: still not code: an errand")
    assert rig.card(card)["status"] == "needs_you"
    assert "start" in {a["id"] for a in rig.card(card)["actions"] if a["enabled"]}
    rig.backend.start(card)  # Retry goes through the same path
    assert len(run.prompts) == 2
    assert start_ids(rig) == [repo_card_id("kuhyx/me-logo")]


def test_t2092_a_second_click_while_it_is_triaged_is_refused(rig: Rig, triage: Make) -> None:
    card = manual(rig)
    run = triage({"label": "research", "reason": "links"})
    run.jobs = []
    rig.backend.start(card)
    with pytest.raises(BackendError) as refused:
        rig.backend.start(card)
    assert refused.value.code == "conflict"
    run.jobs.pop()()
    assert run.service._busy == set()
