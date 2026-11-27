"""T2622: a repo card whose open part is an app-error ticket never runs on the free models (T2445 for parts).

The live kartka card bcf6a474-0 ran its spec turns on `free`: the gate read only the stored note body, while
the ticket's `Error-Signature:` line reached the prompt through the repo task's parts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.board import actions as board_actions
from todoimpl.board.state import RunState
from todoimpl.board.status import Status
from todoimpl.board.types import Credits, Limit
from todoimpl.credits import route
from todoimpl.repotask import files
from todoimpl.repotask.model import Part
from todoimpl.runner import chain, freeok, freeroute
from todoimpl.service.cards import CardTask
from todoimpl.todo_mcp.items import Item

if TYPE_CHECKING:
    from pathlib import Path

TICKET = "Fix kartka: boom\nError: boom\nError-Signature: kartka:8b66d9943a"
CARD = "bcf6a474-0"


def _part(index: int, body: str) -> Part:
    return Part(
        f"e77a1029-{index}", "e77a1029", index, f"part {index}", body, "low", None, human=False, held=False
    )


def _item(*bodies: str) -> Item:
    parts = tuple(_part(i, body) for i, body in enumerate(bodies))
    return Item("bcf6a474", 0, "kuhyx/kartka", "a plain note", "kuhyx/kartka", "todo", None, parts=parts)


@pytest.fixture(autouse=True)
def _free_otherwise(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the repo public, the gateway up and the plan out, so only the parts decide free."""
    monkeypatch.setattr(freeok, "public", lambda _repo: True)
    monkeypatch.setattr(freeok, "gateway_up", lambda: True)
    monkeypatch.setattr(route, "choose", lambda _root, _now: route.Choice(None, 5.0))


def test_t2622_a_repo_card_with_an_error_part_never_routes_free(tmp_path: Path) -> None:
    files.snapshot(tmp_path / CARD, _item("kuhy wants a toolbar", TICKET), "medium")
    st = RunState(task_id=CARD, stage="spec", repo="kuhyx/kartka", note_body="a plain note")
    assert chain.choose(tmp_path, 0.0, st).route is None
    assert not chain.admits(tmp_path, 0.0, CARD)


def test_t2622_a_repo_card_of_kuhy_parts_still_goes_free(tmp_path: Path) -> None:
    files.snapshot(tmp_path / CARD, _item("kuhy wants a toolbar"), "medium")
    st = RunState(task_id=CARD, stage="spec", repo="kuhyx/kartka", note_body="a plain note")
    assert chain.choose(tmp_path, 0.0, st).route == freeroute.FREE


def test_t2622_the_board_offers_no_free_start_for_an_error_part() -> None:
    item = _item(TICKET)
    task = CardTask(CARD, "kuhyx/kartka", "a plain note", "kuhyx/kartka", "todo", "low", None, item)
    limit = Limit(active=True, until=10.0, credits=Credits())
    found = board_actions.actions(task, None, Status.BACKLOG, limit, now=0.0)
    start = next(a for a in found if a.id == "start")
    assert not start.enabled
