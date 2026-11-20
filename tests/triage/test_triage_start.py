"""Start of a new_repo card: the repo is made first, the note gets it, the repo's own card starts."""

import threading
from collections.abc import Callable

import pytest
from conftest import Triage
from servicefakes import Rig
from todoimpl.board.state import load, run_dir
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id
from todoimpl.triage import label, service
from todoimpl.triage.newrepo import NewRepoError

Make = Callable[..., Triage]
NEW = {"label": "new_repo", "name": "pacman-gui", "reason": "asks for a new app"}


def labelled(rig: Rig, triage: Make) -> tuple[str, Triage]:
    card = rig.note("gui for pacman and yay", "a front end", repo=None)
    run = triage(NEW)
    run.service.tick()
    rig.backend.cache.refresh()
    return card, run


def test_t2071_start_makes_the_repo_gives_it_to_the_note_and_starts_the_repo_card(
    rig: Rig, triage: Make
) -> None:
    card, run = labelled(rig, triage)
    rig.backend.start(card)
    new = repo_card_id("kuhyx/pacman-gui")
    assert [(c["name"], c["note"]) for c in run.created] == [("pacman-gui", card[:8])]
    assert run.created[0]["title"] == "gui for pacman and yay"
    assert rig.fake.store.notes[next(n for n in rig.fake.store.notes if n.startswith(card[:8]))].repo == (
        "kuhyx/pacman-gui"
    )
    assert ("start", new, None) in rig.scheduler.calls  # the repo's card runs, the repo-less one is gone
    assert card not in {c["id"] for c in rig.backend.board()["tasks"]}
    assert new in {c["id"] for c in rig.backend.board()["tasks"]}
    stored = label.load(run_dir(rig.root, card))
    assert stored is not None
    assert (stored["repo"], stored["new_card"], stored["label"]) == ("kuhyx/pacman-gui", new, "new_repo")


def test_t2071_a_failed_step_rests_as_a_failed_run_and_retry_goes_again(rig: Rig, triage: Make) -> None:
    card, run = labelled(rig, triage)
    run.provision_error = NewRepoError("gh repo create failed: nope")
    rig.backend.start(card)
    state = load(run_dir(rig.root, card))
    assert state is not None
    assert (state.stage, state.error) == ("failed", "new repo: gh repo create failed: nope")
    assert rig.card(card)["status"] == "needs_you"
    assert rig.scheduler.calls == []
    run.provision_error = None
    rig.backend.start(card)  # Retry: the same path, and the steps already done are skipped by newrepo.json
    assert len(run.created) == 1
    assert ("start", repo_card_id("kuhyx/pacman-gui"), None) in rig.scheduler.calls


def test_t2071_a_second_click_while_the_repo_is_being_made_is_refused(rig: Rig, triage: Make) -> None:
    card, run = labelled(rig, triage)
    run.jobs = []
    rig.backend.start(card)
    with pytest.raises(BackendError) as refused:
        rig.backend.start(card)
    assert refused.value.code == "conflict"
    run.jobs.pop()()  # the first job finishes
    assert len(run.created) == 1
    assert run.service._busy == set()


def test_t2071_any_other_card_starts_through_the_scheduler(rig: Rig, triage: Make) -> None:
    repo_card = rig.note("demo todos", "## a\nx")
    rig.backend.start(repo_card)
    unknown = "deadbeef-0"
    triage().service.start(unknown)
    assert [c[1] for c in rig.scheduler.calls] == [repo_card, unknown]


def test_t2071_the_default_job_runs_on_its_own_thread() -> None:
    done = threading.Event()
    service._spawn(done.set)
    assert done.wait(5)


@pytest.mark.parametrize(("line", "public"), [("visibility: public", True), ("", False)])
def test_t2395_start_passes_the_note_visibility_line_to_the_new_repo(
    rig: Rig, triage: Make, line: str, public: bool
) -> None:
    card = rig.note("gui for pacman and yay", f"a front end\n{line}", repo=None)
    run = triage(NEW)
    run.service.tick()
    rig.backend.cache.refresh()
    rig.backend.start(card)
    assert [c["public"] for c in run.created] == [public]
