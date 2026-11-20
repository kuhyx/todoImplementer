"""A note body edited in the todo app shows on its card at the next board refresh (T2396)."""

from servicefakes import Rig
from todoimpl.todo_mcp.client import TodoClient


def _body(rig: Rig, card: str) -> str:
    found = rig.backend.task(card)
    assert found is not None
    return str(found["body"])


def test_t2396_the_card_view_shows_a_note_body_edited_after_start(rig: Rig) -> None:
    card = rig.note("gui for pacman", "the old text", repo=None)
    rig.run(card, "implement", note_body="the old text")  # Start took this snapshot
    TodoClient(rig.fake.url, rig.fake.token).update_task(card[:8], body="the new text")
    rig.backend.cache.refresh()  # one board refresh cycle
    assert "the new text" in _body(rig, card)
    assert "the old text" not in _body(rig, card)


def test_t2396_the_start_snapshot_still_shows_once_the_note_has_no_text(rig: Rig) -> None:
    card = rig.note("gui for pacman", "the old text", repo=None)
    rig.run(card, "implement", note_body="the old text")
    TodoClient(rig.fake.url, rig.fake.token).update_task(card[:8], body="")
    rig.backend.cache.refresh()
    assert _body(rig, card) == "the old text"
