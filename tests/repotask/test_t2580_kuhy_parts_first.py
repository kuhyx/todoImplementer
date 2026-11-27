"""T2580: kuhy's own part waited behind the automatic tickets of the same note (book-guard, 2026-11-27).

The errors loop appends its tickets to the repo's open note, so they share kuhy's priority; the "easiest
first" tie-break then put every short ticket before kuhy's long part. A part kuhy wrote now always comes
first, then the board's own automatic parts, then other apps' error reports (always low priority).
"""

from __future__ import annotations

from todoimpl.errors import ticket
from todoimpl.errors.record import AppError
from todoimpl.repotask import lane
from todoimpl.repotask.legacy import Older
from todoimpl.service.cards import CardTask
from todoimpl.service.repocards import group_cards
from todoimpl.todo_mcp.model import Task

KUHY = "## Book guard is the most annoying locker\n" + "it is due to the following reasons: " * 25


def _ticket(app: str, sig: str) -> str:
    record = AppError(app, f"kuhyx/{app}", sig, "crash", "TimeoutExpired", 1, "2026-11-27T00:00:00+00:00",
                      "2026-11-27T00:00:00+00:00", 0)  # fmt: skip
    return f"## {ticket.title(record)}\n{ticket.body(record)}"


def _card(body: str, priority: str = "medium") -> CardTask:
    note = Task("a33ecabb", "book-guard", body, "kuhyx/book-guard", "todo", priority, None)
    return group_cards([note], lambda _key: Older())[0]


def test_t2580_kuhys_long_part_runs_before_shorter_app_tickets() -> None:
    body = "\n\n".join([_ticket("book-guard", "52bebe8c02"), KUHY, _ticket("book-guard", "8d1bf8a24b")])
    card = _card(body)
    assert [p.title.startswith("Book guard") for p in card.parts] == [True, False, False]
    assert card.priority == "medium"  # the card's priority is kuhy's part's


def test_t2580_board_tickets_before_app_tickets_after_kuhy() -> None:
    board = _ticket("todoimplementer", "stall-model")
    body = "\n\n".join([_ticket("kartka", "07626036aa"), board, KUHY])
    card = _card(body, "high")
    assert [lane.of_text(p.body) for p in card.parts] == [lane.KUHY, lane.BOARD, lane.APP]
    assert [p.priority for p in card.parts] == ["high", "high", "low"]


def test_t2580_a_card_of_only_app_tickets_is_low() -> None:
    card = _card(_ticket("kartka", "07626036aa"), "high")
    assert card.priority == "low"
    assert lane.of_card(card) == lane.APP
