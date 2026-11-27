"""T2583 edges: the priority pick's refusals, the picker on ended cards, Start with nothing higher waiting."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from todoimpl.board import outrank, prioaction
from todoimpl.board.status import Status
from todoimpl.http.backend import BackendError
from todoimpl.service import priorities
from todoimpl.service.cards import CardTask
from todoimpl.service.view import ItemView
from todoimpl.todo_mcp.items import Item
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from todoimpl.service.backend import ServiceBackend

PLAIN = CardTask(
    "abcd1234-0", "t", "b", None, "todo", "someday", None, Item("abcd1234", 0, "t", "b", None, "todo", None)
)


class _View(ItemView):
    def __init__(self, error: TodoError | None) -> None:  # no client, no cache: only the priority write
        self.error = error
        self.notes: list[str] = []

    def set_note_priority(self, note: str, priority: str) -> None:
        if self.error is not None:
            raise self.error
        self.notes.append(f"{note}:{priority}")


def _backend(view: object, cards: tuple[CardTask, ...] = (PLAIN,)) -> tuple[ServiceBackend, list[int]]:
    pokes: list[int] = []
    cache = SimpleNamespace(snapshot=lambda: SimpleNamespace(tasks=cards), poke=lambda: pokes.append(1))
    return cast("ServiceBackend", SimpleNamespace(cache=cache, scheduler=SimpleNamespace(client=view))), pokes


def test_t2583_a_plain_card_sets_its_own_note_and_refreshes() -> None:
    view = _View(None)
    backend, pokes = _backend(view)
    priorities.set_priority(backend, "abcd1234-0", priority="high")
    assert (view.notes, pokes) == (["abcd1234:high"], [1])


@pytest.mark.parametrize(("card", "view", "code"), [("zzzz9999-0", _View(None), "not_found"),
                                                     ("abcd1234-0", object(), "not_found")])  # fmt: skip
def test_t2583_an_unknown_card_or_a_board_without_a_todo_view_is_refused(
    card: str, view: Any, code: str
) -> None:
    with pytest.raises(BackendError) as caught:
        priorities.set_priority(_backend(view)[0], card, priority="low")
    assert caught.value.code == code


def test_t2583_a_todo_app_that_fails_is_upstream_and_the_cache_still_refreshes() -> None:
    backend, pokes = _backend(_View(TodoError("down")))
    with pytest.raises(BackendError) as caught:
        priorities.set_priority(backend, "abcd1234-0", priority="low")
    assert (caught.value.code, pokes) == ("upstream_unavailable", [1])


def test_t2583_the_picker_leaves_ended_cards_and_shows_an_odd_priority_as_medium() -> None:
    assert prioaction.action(PLAIN, Status.DONE) == []
    (pick,) = prioaction.action(PLAIN, Status.BACKLOG)
    assert (pick.value, pick.enabled) == ("medium", True)


def test_t2583_start_with_nothing_higher_or_no_enabled_start_is_left_alone() -> None:
    waiting = [{"id": "aaaa1111-0", "title": "x", "priority": "low", "lane": "kuhy"}]
    card: dict[str, Any] = {
        "id": "bbbb2222-0",
        "priority": "medium",
        "actions": [{"id": "start", "enabled": True}],
    }
    outrank.mark(card, waiting)
    assert "waits" not in card["actions"][0]
    off: dict[str, Any] = {
        "id": "bbbb2222-0",
        "priority": "low",
        "actions": [{"id": "start", "enabled": False}],
    }
    outrank.mark(off, [{**waiting[0], "priority": "high"}])
    assert "waits" not in off["actions"][0]
