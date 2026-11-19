"""Done manually: the card rests in Done, every note is closed, no Claude turn runs (T2064)."""

from __future__ import annotations

import pytest
from contract_lib import validate
from repofakes import Rig
from todoimpl.board.state import RunState, save
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner import stopping
from todoimpl.runner.files import write_json
from todoimpl.runner.scheduler import RunnerError
from todoimpl.service import ServiceBackend, TaskCache, board_fetch

ACTION = {"id": "done-manually", "label": "Done manually", "enabled": True, "reason": None, "confirm": True}


def _note(rig: Rig, note8: str) -> tuple[str, str | None]:
    found = next(n for k, n in rig.fake.store.notes.items() if k.startswith(note8))
    return found.status, found.evidence


def _offered(card: dict[str, object]) -> dict[str, object] | None:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next((a for a in actions if a["id"] == "done-manually"), None)


def test_t2064_a_repo_card_closes_every_note_and_rests_in_done_manually(rig: Rig) -> None:
    repo = rig.repo()
    first = rig.note(repo, "Wire the reporter", "## a\nx\n\n## b (Tk gate)\ny")
    second = rig.note(repo, "other note", "z")
    card = rig.card(repo)
    assert _offered(card) == ACTION
    rig.backend.done_manually(card["id"])
    assert [_note(rig, n)[0] for n in (first, second)] == ["done", "done"]  # closed, never abandoned
    assert all("manually" in str(_note(rig, n)[1]) for n in (first, second))
    assert rig.state(card["id"]).stage == "done_manually"
    assert rig.world.calls() == []  # no Claude turn
    rig.cache.refresh()
    validate("board", rig.backend.board())
    shown = rig.card(repo)
    assert (shown["status"], shown["column"], shown["stage"]) == ("done_manually", "done", "done_manually")
    assert shown["actions"] == []


def test_t2064_the_done_card_survives_a_server_restart(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    rig.backend.done_manually(card)
    fresh = TaskCache(board_fetch(rig.client, rig.world.root))
    fresh.refresh()
    again = ServiceBackend(fresh, rig.sched, rig.world.root, "b2").board()
    assert [(c["id"], c["status"]) for c in again["tasks"]] == [(card, "done_manually")]


def test_t2064_a_live_turn_is_stopped_and_its_cancel_does_not_overwrite_the_stage(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    rig.script(card, ({"_fake": "sleep", "sec": 30},))
    rig.sched.start(card)
    rig.until(lambda: card in rig.sched.running())
    rig.until(lambda: bool(rig.world.calls()))
    rig.backend.done_manually(card)
    rig.until(lambda: card not in rig.sched.running())
    rig.until(lambda: rig.state(card).stage == "done_manually")
    assert _note(rig, note)[0] == "done"
    assert len(rig.world.calls()) == 1  # the one turn it had, no resume


def test_t2064_a_queued_run_leaves_the_queue(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    rig.sched.locks.acquire(repo, "2d0704cd-7")  # another run holds the repo: ours waits queued
    rig.sched.start(card)
    rig.until(lambda: rig.sched.lock_waits() == {card: "2d0704cd-7"})
    rig.backend.done_manually(card)
    assert rig.state(card).stage == "done_manually"
    assert rig.sched.lock_waits() == {}
    assert rig.world.calls() == []


def test_t2064_a_section_card_is_done_and_the_other_sections_stay_open(rig: Rig) -> None:
    repo = rig.repo()
    held = rig.note(repo, "held note", "## one\nx\n\n## two\ny")
    save(rig.run_dir(f"{held}-0"), RunState(task_id=f"{held}-0", stage="implement", repo=repo, error="boom"))
    rig.cache.refresh()
    card = next(c for c in rig.backend.board()["tasks"] if c["id"] == f"{held}-0")
    assert _offered(card) == ACTION
    rig.backend.done_manually(f"{held}-0")
    text = next(n.text for k, n in rig.fake.store.notes.items() if k.startswith(held))
    assert ("## [x] one" in text, "## [x] two" in text) == (True, False)
    assert _note(rig, held)[0] == "todo"  # section two is still open
    assert rig.state(f"{held}-0").stage == "done_manually"


def test_t2064_a_note_without_a_repo_is_closed_too(rig: Rig) -> None:
    idea = rig.note(None, "wysłać jpk")
    card = next(c for c in rig.backend.board()["tasks"] if c["id"] == f"{idea}-0")
    assert _offered(card) == ACTION
    rig.backend.done_manually(card["id"])
    assert _note(rig, idea)[0] == "done"


def test_t2064_a_cancelled_card_can_be_done_manually(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="cancelled", repo=repo, extra={"repotask": True}))
    assert _offered(rig.card(repo)) == ACTION
    rig.backend.done_manually(card)
    assert (_note(rig, note)[0], rig.state(card).stage) == ("done", "done_manually")


def test_t2064_a_push_in_flight_is_not_interrupted(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="shipping", repo=repo, extra={"repotask": True}))
    offered = _offered(rig.card(repo))
    assert offered is not None
    assert (offered["enabled"], offered["reason"]) == (False, "shipping cannot be stopped")
    with pytest.raises(BackendError, match="shipping"):
        rig.backend.done_manually(card)
    assert _note(rig, note)[0] == "todo"  # refused before any write


def test_t2064_an_unknown_card_is_refused(rig: Rig) -> None:
    with pytest.raises(BackendError, match="unknown task"):
        rig.backend.done_manually("nope0000-0")


def test_t2064_a_new_part_after_done_manually_starts_a_new_cycle(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    rig.backend.done_manually(card)
    rig.note(repo, "later note", "y")
    again = rig.card(repo)
    assert (again["status"], again["stage"]) == ("backlog", None)
    start = next(a for a in again["actions"] if a["id"] == "start")
    assert start["enabled"] is True
    rig.script(card, ({"_fake": "sleep", "sec": 30},))
    rig.sched.start(card)  # the run dir says done_manually: Start is the next cycle, not a conflict
    assert rig.state(card).extra["cycle"] == 2
    rig.sched.cancel(card)


def test_t2064_a_card_that_is_already_done_is_refused_before_any_note_is_closed(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="shipped", repo=repo, extra={"repotask": True}))
    with pytest.raises(BackendError, match="already shipped"):
        rig.backend.done_manually(card)
    assert _note(rig, note)[0] == "todo"


def test_t2064_the_scheduler_refuses_a_push_in_flight_and_a_card_that_is_done(rig: Rig) -> None:
    repo = rig.repo()
    card = repo_card_id(repo)
    for stage, text in (
        ("shipping", "shipping"),
        ("shipped", "already shipped"),
        ("done_manually", "already"),
    ):
        save(rig.run_dir(card), RunState(task_id=card, stage=stage, repo=repo))
        with pytest.raises(RunnerError, match=text):
            rig.sched.done_manually(card)
    assert not rig.run_dir(card).joinpath(stopping.FILE).exists()


def test_t2064_a_click_a_restart_cut_is_settled_when_the_server_starts(rig: Rig) -> None:
    repo = rig.repo()
    cut, live = repo_card_id(repo), "aaaa1111-0"
    save(rig.run_dir(cut), RunState(task_id=cut, stage="implement", repo=repo))
    write_json(rig.run_dir(cut) / stopping.FILE, {"repo": repo, "title": "demo", "repotask": True})
    write_json(rig.run_dir(live) / stopping.FILE, {})
    with rig.sched._cv:
        rig.sched._active.add(live)  # a recovered drive is already running: it is stopped, not settled
    stopping.recover(rig.sched)
    assert rig.state(cut).stage == "done_manually"
    assert (rig.state(cut).extra["repotask"], rig.state(cut).extra["repotask_title"]) == (True, "demo")
    assert live in rig.sched._cancel
    assert stopping.pending(rig.world.root) == [live]
    with rig.sched._cv:
        rig.sched._active.discard(live)
        rig.sched._cancel.discard(live)


def test_t2064_a_board_without_an_item_view_refuses_and_writes_nothing(rig: Rig) -> None:
    class Bare:  # a scheduler with no todo view to close notes through
        client = None

    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    other = ServiceBackend(rig.cache, Bare(), rig.world.root, "b3")  # type: ignore[arg-type]
    with pytest.raises(BackendError, match="no todo view"):
        other.done_manually(repo_card_id(repo))
    assert _note(rig, note)[0] == "todo"
