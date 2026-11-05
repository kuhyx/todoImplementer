"""Card ids and the Item-as-task adapter."""

import re

from todoimpl.service.cards import CardTask, card_id, card_tasks
from todoimpl.todo_mcp.model import Task

ITEM_ID = re.compile(r"^[A-Za-z0-9]{8}-[0-9]+$")


def note(body: str) -> Task:
    return Task("abcdef12-3456", "demo todos", body, "kuhyx/demo", "todo", "high", "make")


def test_card_id_is_note_id8_dash_section_index() -> None:
    assert card_id("abcdef12-3456", 0) == "abcdef12-0"
    assert card_id("abcdef12", 7) == "abcdef12-7"
    assert ITEM_ID.match(card_id("abcdef12", 12))


def test_two_sections_become_two_cards_with_note_priority() -> None:
    cards = card_tasks(note("## a\nbody a\n## b\nbody b"))
    assert [(c.id, c.title, c.body, c.priority) for c in cards] == [
        ("abcdef12-0", "a", "body a", "high"),
        ("abcdef12-1", "b", "body b", "high"),
    ]
    assert cards[1].item.note_id == "abcdef12-3456"
    assert cards[1].item.index == 1
    assert isinstance(cards[0], CardTask)


def test_note_without_sections_is_one_card_with_its_done_check() -> None:
    (card,) = card_tasks(note("plain"))
    assert (card.id, card.title, card.done_check) == ("abcdef12-0", "demo todos", "make")
