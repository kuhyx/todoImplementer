"""Won't do: kuhy drops a card nobody will work on; every note behind it is abandoned (T2045)."""

from __future__ import annotations

import pytest
from repofakes import Rig
from todoimpl.board.state import RunState, save
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id


def _status(rig: Rig, note8: str) -> str:
    return next(n.status for k, n in rig.fake.store.notes.items() if k.startswith(note8))


def _wont(card: dict[str, object]) -> dict[str, object] | None:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next((a for a in actions if a["id"] == "wont"), None)


def test_t2045_wont_on_a_repo_card_abandons_every_note_and_the_card_leaves_the_board(rig: Rig) -> None:
    repo = rig.repo()
    first = rig.note(repo, "Wire the shared app-errors reporter", "## a\nx\n\n## b (Tk gate)\ny")
    second = rig.note(repo, "other note", "z")
    card = rig.card(repo)
    assert card["status"] == "backlog"
    wont = {"id": "wont", "label": "Won't do", "enabled": True, "reason": None, "confirm": True}
    assert _wont(card) == wont
    rig.backend.wont(card["id"])
    assert (_status(rig, first), _status(rig, second)) == ("abandoned", "abandoned")
    rig.cache.refresh()
    assert all(c["id"] != repo_card_id(repo) for c in rig.backend.board()["tasks"])


def test_wont_refuses_before_any_write_when_a_note_has_a_part_on_another_card(rig: Rig) -> None:
    repo = rig.repo()
    loose = rig.note(repo, "loose note", "x")
    held = rig.note(repo, "held note", "## one\nx\n\n## two\ny")
    save(rig.run_dir(f"{held}-1"), RunState(task_id=f"{held}-1", stage="implement", repo=repo))
    rig.cache.refresh()
    with pytest.raises(BackendError, match=f"{held}-1"):
        rig.backend.wont(repo_card_id(repo))
    assert (_status(rig, loose), _status(rig, held)) == ("todo", "todo")


def test_wont_on_a_resting_run_cancels_it_and_abandons_the_section_note(rig: Rig) -> None:
    repo = rig.repo()
    held = rig.note(repo, "held note", "x")
    card = f"{held}-0"
    save(rig.run_dir(card), RunState(task_id=card, stage="implement", repo=repo, error="boom"))
    rig.cache.refresh()
    found = next(c for c in rig.backend.board()["tasks"] if c["id"] == card)
    assert found["status"] == "needs_you"
    assert _wont(found) is not None
    rig.backend.wont(card)
    assert rig.state(card).stage == "cancelled"
    assert _status(rig, held) == "abandoned"


def test_wont_on_a_cancelled_repo_run_only_abandons_the_note(rig: Rig) -> None:
    repo = rig.repo()
    note = rig.note(repo, "a note", "x")
    card = repo_card_id(repo)
    save(rig.run_dir(card), RunState(task_id=card, stage="cancelled", repo=repo, extra={"repotask": True}))
    found = rig.card(repo)
    assert found["status"] == "cancelled"
    assert _wont(found) is not None
    rig.backend.wont(card)
    assert rig.state(card).stage == "cancelled"
    assert _status(rig, note) == "abandoned"


def test_wont_on_an_unknown_card_is_refused(rig: Rig) -> None:
    with pytest.raises(BackendError, match="unknown task"):
        rig.backend.wont("nope0000-0")
