"""ItemView: the Scheduler's TodoClient look-alike (section cards: sections an older run still owns)."""

import pytest
from servicefakes import Rig
from todoimpl.runner import retry
from todoimpl.service import ItemView
from todoimpl.service.cache import TaskCache
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError


def view(rig: Rig) -> ItemView:
    return ItemView(TodoClient(rig.fake.url, rig.fake.token), rig.backend.cache)


def test_get_task_returns_the_fresh_section(rig: Rig) -> None:
    first, second = rig.sections("## a\nbody a\n## b\nbody b")
    rig.fake.store.notes[next(iter(rig.fake.store.notes))].text = "demo todos\n\n## a\nbody a\n## b\nCHANGED"
    got = view(rig).get_task(second)
    assert (got.id, got.body, got.item.note_id[:8]) == (second, "CHANGED", first[:8])


def test_unknown_card_and_vanished_section_raise(rig: Rig) -> None:
    second = rig.sections("## a\nx\n## b\ny")[1]
    with pytest.raises(TodoError, match="unknown task"):
        view(rig).get_task("nope0000")
    rig.fake.store.notes[next(iter(rig.fake.store.notes))].text = "demo todos\n\n## a\nx"
    with pytest.raises(TodoError, match="moved or gone"):
        view(rig).get_task(second)


def test_list_tasks_filters_the_cached_cards(rig: Rig) -> None:
    rig.note(title="one", repo="kuhyx/a")
    rig.note(title="two", repo="kuhyx/b", status="in_progress")
    v = view(rig)
    assert len(v.list_tasks()) == 2
    assert [t.title for t in v.list_tasks(repo="kuhyx/b")] == ["b"]
    assert [t.title for t in v.list_tasks(status="in progress")] == ["b"]


def test_list_tasks_raises_the_refresh_error(rig: Rig) -> None:
    with pytest.raises(TodoError, match="not loaded"):
        view(rig).list_tasks()


def test_update_task_changes_note_fields_only(rig: Rig) -> None:
    (card,) = rig.sections("only part", title="one")
    updated = view(rig).update_task(card, status="in progress")
    assert updated.status == "in progress"
    with pytest.raises(TodoError, match="only"):
        view(rig).update_task(card, body="x")


def test_close_task_marks_one_section_and_pokes(rig: Rig) -> None:
    first, _ = rig.sections("## a\nx\n## b\ny")
    view(rig).close_task(first, "ran: ok")
    (note,) = rig.fake.store.notes.values()
    assert "## [x] a" in note.text
    assert note.status == "todo"


def test_t1109_add_task_passes_through_and_pokes(rig: Rig) -> None:
    rig.sections("## a\nx")
    added = view(rig).add_task("kuhyx/demo", "Demo — rest: C2", "- C2: open")
    assert added.repo == "kuhyx/demo"
    assert rig.backend.cache._wake.is_set()
    rig.backend.cache.refresh()
    parts = {p.title for t in rig.backend.cache.snapshot().tasks for p in t.parts}
    assert "Demo — rest: C2" in parts


def test_t1807_a_card_asked_before_the_first_load_is_a_transient_miss(rig: Rig) -> None:
    (card,) = rig.sections("only part", title="one")
    cold = ItemView(TodoClient(rig.fake.url, rig.fake.token), TaskCache(list))
    with pytest.raises(TodoError) as caught:
        cold.get_task(card)
    assert retry.is_transient(str(caught.value)), caught.value


def test_t1812_a_retried_follow_up_never_adds_the_same_section_twice(rig: Rig) -> None:
    rig.sections("## a\nx")
    first = view(rig).add_task("kuhyx/demo", "Demo — rest: C2", "- C2: open")
    again = view(rig).add_task("kuhyx/demo", "Demo — rest: C2", "- C2: open")
    assert again.id == first.id
    (note,) = rig.fake.store.notes.values()
    assert note.text.count("Demo — rest: C2") == 1


def test_t1812_a_finished_follow_up_does_not_block_a_new_one(rig: Rig) -> None:
    note_id = rig.sections("## a\nx")[0][:8]
    view(rig).add_task("kuhyx/demo", "Demo — rest: C2", "- C2: open")
    rig.run(f"{note_id}-1", "gate")  # the follow-up is the note's second section
    rig.backend.cache.refresh()
    done = next(t for t in rig.backend.cache.snapshot().tasks if t.title == "Demo — rest: C2")
    view(rig).close_task(done.id, "ran: ok")
    view(rig).add_task("kuhyx/demo", "Demo — rest: C2", "- C2: open again")
    (note,) = rig.fake.store.notes.values()
    assert note.text.count("Demo — rest: C2") == 2


def test_t1815_cancel_abandons_the_note_only_when_no_other_section_is_open(rig: Rig) -> None:
    first, second = rig.sections("## a\nx\n\n## b\ny")
    assert view(rig).abandon(first) is False
    (note,) = rig.fake.store.notes.values()
    assert note.status == "todo"
    view(rig).close_task(second, "ran: ok")
    assert view(rig).abandon(first) is True
    assert note.status == "abandoned"
