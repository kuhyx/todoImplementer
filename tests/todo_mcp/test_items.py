"""Per-section items of a note: splitting, done markers, close_item."""

from __future__ import annotations

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import Task, TodoClient, TodoError
from todoimpl.todo_mcp.items import Item, mark_done, split_items


def _task(body: str, *, check: str | None = None, status: str = "todo") -> Task:
    return Task("abcdef12", "r todos", body, "kuhyx/r", status, "medium", check)


def test_note_without_sections_is_one_item() -> None:
    items = split_items(_task("just text", check="make"))
    assert items == [Item("abcdef12", 0, "r todos", "just text", "kuhyx/r", "todo", "make")]


def test_sections_split_with_preamble_dropped_and_status_inherited() -> None:
    body = "preamble\n\n## a\nbody a\n\n## b\n\n### sub\nmore\n## c"
    items = split_items(_task(body, status="in progress"))
    assert [(i.index, i.title, i.body, i.status) for i in items] == [
        (0, "a", "body a", "in progress"),
        (1, "b", "### sub\nmore", "in progress"),
        (2, "c", "", "in progress"),
    ]
    assert items[1].note_id == "abcdef12"
    assert items[1].repo == "kuhyx/r"


def test_fenced_heading_is_not_a_section() -> None:
    body = "## a\n```\n## not a section\n```\nafter\n## b"
    assert [i.title for i in split_items(_task(body))] == ["a", "b"]


def test_done_marker_and_closed_line() -> None:
    body = "## [x] a\nclosed: abc exit 0\ntext\n## b"
    done, todo = split_items(_task(body))
    assert (done.title, done.status, done.body) == ("a", "done", "text")
    assert todo.status == "todo"


def test_section_done_check_line_else_single_note_check_else_none() -> None:
    own = split_items(_task("## a\ndone_check: `make a`\n## b", check="note"))
    assert [i.done_check for i in own] == ["make a", None]
    assert split_items(_task("## a\ntext", check="note"))[0].done_check == "note"
    assert split_items(_task("## a\ntext\n## b", check="note"))[0].done_check is None


def test_mark_done_rewrites_heading_only() -> None:
    body = "pre\n## a\nx\n## b\ny"
    assert mark_done(body, 1, "sha  exit\n0") == "pre\n## a\nx\n## [x] b\nclosed: sha exit 0\ny"


def _seed(fake: FakeTodoMcp, body: str, **fields: str | None) -> str:
    return fake.seed("kuhyx/r", "r todos", body, **fields)


def test_close_item_marks_section_and_keeps_note_open(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\nx\n\n## b\ny")
    item = split_items(client.get_task(note[:8]))[0]
    client.close_item(item, "abc1234 exit 0")
    stored = fake.store.notes[note]
    assert stored.status == "todo"
    assert stored.text == "r todos\n\n## [x] a\nclosed: abc1234 exit 0\nx\n\n## b\ny"
    assert [c[0] for c in fake.calls].count("close_task") == 0


def test_close_last_section_closes_note(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\nx\n## [x] b\nclosed: e\ny")
    client.close_item(split_items(client.get_task(note[:8]))[0], "sha exit 0")
    assert (fake.store.notes[note].status, fake.store.notes[note].evidence) == ("done", "sha exit 0")


def test_close_item_on_note_without_sections_closes_note(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "")
    client.close_item(split_items(client.get_task(note[:8]))[0], "sha exit 0")
    assert fake.store.notes[note].status == "done"
    assert [c[0] for c in fake.calls].count("update_task") == 0


def test_close_item_twice_is_idempotent(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\n## b")
    item = split_items(client.get_task(note[:8]))[0]
    client.close_item(item, "e1")
    text = fake.store.notes[note].text
    client.close_item(item, "e2")
    assert fake.store.notes[note].text == text
    assert fake.store.notes[note].status == "todo"


def test_close_item_fails_closed(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\n## b")
    item = split_items(client.get_task(note[:8]))[0]
    with pytest.raises(TodoError, match="evidence"):
        client.close_item(item, " ")
    moved = Item(item.note_id, 1, "a", "", item.repo, "todo", None)
    with pytest.raises(TodoError, match="moved"):
        client.close_item(moved, "e")
    gone = Item(item.note_id, 5, "a", "", item.repo, "todo", None)
    with pytest.raises(TodoError, match="moved"):
        client.close_item(gone, "e")
    assert fake.store.notes[note].text == "r todos\n\n## a\n## b"
