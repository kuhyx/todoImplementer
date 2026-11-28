"""T2583: kuhy changes a card's priority from the board, and Start asks first while a higher card waits."""

from __future__ import annotations

from typing import Any

import pytest
from contract_lib import validate
from repofakes import Rig
from todoimpl.errors import ticket
from todoimpl.errors.record import AppError
from todoimpl.http import bodies
from todoimpl.http.backend import BackendError

RECORD = AppError("demo", "kuhyx/demo", "07626036aa", "crash", "boom", 1, "2026-11-27T00:00:00+00:00",
                  "2026-11-27T00:00:00+00:00", 0)  # fmt: skip
TICKET = f"## {ticket.title(RECORD)}\n{ticket.body(RECORD)}"


def _action(card: dict[str, Any], key: str) -> dict[str, Any] | None:
    return next((a for a in card["actions"] if a["id"] == key), None)


def _priority(rig: Rig, note8: str) -> str:
    return next(n.priority for k, n in rig.fake.store.notes.items() if k.startswith(note8))


def test_t2583_a_card_offers_its_priority_and_a_pick_sets_every_note_behind_it(rig: Rig) -> None:
    repo = rig.repo()
    first = rig.note(repo, "one", "x", priority="low")
    second = rig.note(repo, "two", "y", priority="medium")
    card = rig.card(repo)
    validate("board", rig.backend.board())
    pick = _action(card, "priority")
    assert pick is not None
    assert (pick["enabled"], pick["value"], [c["id"] for c in pick["choices"]]) == (
        True, "medium", ["high", "medium", "low"],
    )  # fmt: skip
    assert card["lane"] == "kuhy"
    rig.backend.priority(card["id"], priority="high")
    assert (_priority(rig, first), _priority(rig, second)) == ("high", "high")
    rig.cache.refresh()
    assert rig.card(repo)["priority"] == "high"


def test_t2583_a_card_of_only_app_reports_cannot_be_raised(rig: Rig) -> None:
    repo = rig.repo()
    rig.note(repo, "errors", TICKET, priority="high")
    card = rig.card(repo)
    pick = _action(card, "priority")
    assert pick is not None
    assert (card["priority"], card["lane"], pick["enabled"]) == ("low", "app", False)
    assert pick["reason"]
    with pytest.raises(BackendError) as caught:
        rig.backend.priority(card["id"], priority="high")
    assert caught.value.code == "disabled"


def test_t2583_start_names_the_higher_backlog_card_it_would_jump(rig: Rig) -> None:
    high = rig.repo("alpha")
    low = rig.repo("beta")
    rig.note(high, "urgent", "Done: x", priority="high")
    rig.note(low, "later", "Done: y", priority="low")
    top, under = rig.card(high), rig.card(low)
    assert _action(top, "start") is not None
    assert "waits" not in (_action(top, "start") or {})
    assert (_action(under, "start") or {})["waits"] == {"id": top["id"], "title": "alpha", "priority": "high"}
    detail = rig.backend.task(under["id"])
    assert detail is not None
    validate("task", detail)
    assert (_action(detail["card"], "start") or {})["waits"]["id"] == top["id"]


def test_t2583_the_priority_body_is_checked() -> None:
    assert bodies.check("priority", {"priority": "high"}) is None
    assert bodies.check("priority", {"priority": "urgent"}) == "priority must be one of high, medium, low"
    assert bodies.check("priority", {}) == "body must be exactly {priority}"
