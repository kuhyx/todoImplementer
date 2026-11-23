"""T2529: a card being created (its repo made, or its note triaged) leaves Backlog and offers no Start."""

from collections.abc import Callable

from conftest import Triage
from contract_lib import validate
from servicefakes import Rig
from test_triage_start import NEW, labelled

Make = Callable[..., Triage]


def test_t2529_a_card_whose_repo_is_being_made_is_working_with_start_disabled(rig: Rig, triage: Make) -> None:
    card, run = labelled(rig, triage)
    run.jobs = []
    rig.backend.start(card)
    shown = rig.card(card)
    assert (shown["status"], shown["column"], shown["current"]) == ("working", "running", "being created")
    assert [(a["id"], a["enabled"], a.get("reason")) for a in shown["actions"]] == [
        ("start", False, "being created")
    ]
    run.jobs.pop()()  # the repo is made: the repo-less card is gone, the repo's own card takes over
    assert card not in {c["id"] for c in rig.backend.board()["tasks"]}


def test_t2529_a_pressed_note_being_triaged_is_working_too(rig: Rig, triage: Make) -> None:
    card = rig.note("an idea", "do a thing", repo=None)
    run = triage(NEW)
    run.jobs = []
    rig.backend.start(card)  # no label yet: Start triages it first (T2092)
    assert (rig.card(card)["status"], run.service.busy()) == ("working", frozenset({card}))
    run.jobs.pop()()
    assert run.service.busy() == frozenset()


def test_t2529_the_board_with_a_card_being_created_matches_the_contract(rig: Rig, triage: Make) -> None:
    card, run = labelled(rig, triage)
    run.jobs = []
    rig.backend.start(card)
    validate("board", rig.backend.board())


def test_t2529_retry_of_a_failed_creation_is_being_created_too(rig: Rig, triage: Make) -> None:
    card, run = labelled(rig, triage)
    run.provision_error = RuntimeError("gh repo create failed")
    rig.backend.start(card)
    assert rig.card(card)["status"] == "needs_you"
    run.provision_error, run.jobs = None, []
    rig.backend.start(card)  # Retry
    shown = rig.card(card)
    assert (shown["status"], shown["current"], shown["needs"]) == ("working", "being created", None)
