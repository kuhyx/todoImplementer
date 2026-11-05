"""ItemView: the Scheduler's TodoClient look-alike."""

import pytest
from servicefakes import Rig
from todoimpl.service import ItemView
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError


def view(rig: Rig) -> ItemView:
    return ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache)


def test_get_task_returns_the_fresh_section(rig: Rig) -> None:
    note = rig.note(body="## a\nbody a\n## b\nbody b")
    second = next(t for t in rig.backend.cache.snapshot().tasks if t.title == "b")
    rig.fake.store.notes[next(iter(rig.fake.store.notes))].text = "demo todos\n\n## a\nbody a\n## b\nCHANGED"
    got = view(rig).get_task(second.id)
    assert (got.id, got.body, got.item.note_id[:8]) == (second.id, "CHANGED", note[:8])


def test_unknown_card_and_vanished_section_raise(rig: Rig) -> None:
    rig.note(body="## a\nx\n## b\ny")
    second = next(t for t in rig.backend.cache.snapshot().tasks if t.title == "b")
    with pytest.raises(TodoError, match="unknown task"):
        view(rig).get_task("nope0000")
    rig.fake.store.notes[next(iter(rig.fake.store.notes))].text = "demo todos\n\n## a\nx"
    with pytest.raises(TodoError, match="moved or gone"):
        view(rig).get_task(second.id)


def test_list_tasks_filters_the_cached_cards(rig: Rig) -> None:
    rig.note(title="one", repo="kuhyx/a")
    rig.note(title="two", repo="kuhyx/b", status="in_progress")
    v = view(rig)
    assert len(v.list_tasks()) == 2
    assert [t.title for t in v.list_tasks(repo="kuhyx/b")] == ["two"]
    assert [t.title for t in v.list_tasks(status="in progress")] == ["two"]


def test_list_tasks_raises_the_refresh_error(rig: Rig) -> None:
    with pytest.raises(TodoError, match="not loaded"):
        view(rig).list_tasks()


def test_update_task_changes_note_fields_only(rig: Rig) -> None:
    rig.note(title="one")
    card = rig.backend.cache.snapshot().tasks[0]
    updated = view(rig).update_task(card.id, status="in progress")
    assert updated.status == "in progress"
    with pytest.raises(TodoError, match="only"):
        view(rig).update_task(card.id, body="x")


def test_close_task_marks_one_section_and_pokes(rig: Rig) -> None:
    rig.note(body="## a\nx\n## b\ny")
    first = rig.backend.cache.snapshot().tasks[0]
    view(rig).close_task(first.id, "ran: ok")
    (note,) = rig.fake.store.notes.values()
    assert "## [x] a" in note.text
    assert note.status == "todo"
