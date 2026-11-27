"""Which parts kuhy may still edit (856c0f0a): the board offers the edit only where it can succeed."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from contract_lib import validate
from todoimpl.board.board import build_task
from todoimpl.board.card import Context, build_card
from todoimpl.board.partedit import REACHED, REASONS, with_edit
from todoimpl.board.state import RunState
from todoimpl.board.status import Status
from todoimpl.repotask.model import Part
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item


def part(key: str, **fields: bool) -> Part:
    note, _, index = key.partition("-")
    human, held = fields.get("human", False), fields.get("held", False)
    return Part(key, note, int(index), f"t {key}", f"body of {key}", "medium", None, human, held)


def card_of(*parts: Part) -> CardTask:
    item = Item("deadbeef", 0, "demo", "body", "kuhyx/demo", "todo", None, "kuhy", parts=parts)
    return CardTask("deadbeef-0", "demo", "body", "kuhyx/demo", "todo", "medium", None, item)


def shown(state: str) -> dict[str, Any]:
    return {"id": "aaaa1111-0", "title": "t", "state": state, "steps": None}


def edits(parts: list[dict[str, Any]]) -> list[tuple[bool, str | None]]:
    return [(p["edit"]["enabled"], p["edit"]["reason"]) for p in parts]


def test_a_backlog_card_offers_every_unticked_part_but_a_held_one() -> None:
    card = build_card(
        card_of(part("aaaa1111-0"), part("bbbb2222-0", human=True), part("cccc3333-0", held=True)),
        None,
        Context(),
    )
    validate("common", card, "task_card")
    assert card["status"] == "backlog"
    assert edits(card["parts"]) == [(True, None), (True, None), (False, REASONS["held"])]
    assert "body" not in card["parts"][0]  # the board stays small: the text rides on the detail only


def test_a_working_run_holds_its_current_part_and_its_ticked_ones() -> None:
    run = RunState(task_id="deadbeef-0", stage="implement", extra={"parts_ticks": {"done": ["aaaa1111-0"]}})
    parts = (part("aaaa1111-0"), part("aaaa1111-1"), part("aaaa1111-2"))
    card = build_card(card_of(*parts), run, Context(live=frozenset({"deadbeef-0"}), now=1.0))
    assert [p["state"] for p in card["parts"]] == ["done", "working", "todo"]
    assert edits(card["parts"]) == [(False, REASONS["done"]), (False, REACHED), (True, None)]


def test_a_live_run_that_is_not_working_still_holds_the_part_it_reached() -> None:
    parts = [shown("human"), shown("todo"), shown("todo")]
    assert edits(with_edit(parts, Status.NEEDS_YOU)) == [(True, None), (False, REACHED), (True, None)]


def test_a_resting_card_holds_nothing() -> None:
    for status in (Status.BACKLOG, Status.YOURS):
        assert edits(with_edit([shown("todo"), shown("todo")], status)) == [(True, None), (True, None)]


def test_the_detail_carries_each_part_text_for_the_editor(tmp_path: Path) -> None:
    detail = build_task(card_of(part("aaaa1111-0"), part("bbbb2222-1")), None, tmp_path, Context())
    validate("task", detail)
    assert [p["body"] for p in detail["card"]["parts"]] == ["body of aaaa1111-0", "body of bbbb2222-1"]
