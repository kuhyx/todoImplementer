"""T2530: a repo card whose run was cancelled keeps its open notes on the board, in Backlog, not Done."""

from __future__ import annotations

from todoimpl.board.card import Context, build_card
from todoimpl.board.state import RunState
from todoimpl.repotask.model import Part
from todoimpl.runner.stopping import refusal
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item


def _card(status: str = "todo") -> CardTask:
    part = Part("aaaa1111-0", "aaaa1111", 0, "fix it", "b", "medium", None, human=False, held=False)
    item = Item("deadbeef", 0, "demo", "body", "kuhyx/demo", status, None, "kuhy", parts=(part,))
    return CardTask("deadbeef-0", "demo", "body", "kuhyx/demo", status, "medium", None, item)


def _cancelled() -> RunState:
    return RunState(task_id="deadbeef-0", stage="cancelled", session_id="s", extra={"repotask": True})


def test_t2530_a_cancelled_repo_card_with_open_parts_is_backlog_and_can_start() -> None:
    shown = build_card(_card(), _cancelled(), Context())
    assert (shown["status"], shown["column"], shown["current"]) == ("backlog", "backlog", "cancelled")
    buttons = {a["id"]: a["enabled"] for a in shown["actions"]}
    assert (buttons["start"], buttons["wont"], buttons["done-manually"]) == (True, True, True)
    assert "send" not in buttons  # a cancelled run takes no note; Start is the way back
    assert refusal("cancelled", repotask=True) is None  # Done manually can succeed from here


def test_t2530_a_cancelled_card_whose_notes_are_closed_stays_done() -> None:
    assert build_card(_card("abandoned"), _cancelled(), Context())["column"] == "done"
    assert build_card(_card("done"), _cancelled(), Context())["status"] == "done"
