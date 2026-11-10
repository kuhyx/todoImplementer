"""An umbrella note is ONE item: splitting, closing and ticking go through the todo client."""

from __future__ import annotations

from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import split_items
from umbrellafakes import sample


def _seed(fake: FakeTodoMcp, repo: str | None = None) -> str:
    return fake.seed(repo, "Make the repos text-free", sample().split("\n", 1)[1])


def test_an_umbrella_note_is_a_single_item_with_its_whole_body(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = client.get_task(_seed(fake)[:8])
    (item,) = split_items(note)
    assert (item.index, item.repo, item.title) == (0, None, "Make the repos text-free")
    assert "## kuhyx/alpha (aaaa1111)" in item.body
    assert item.body.startswith("Umbrella: per-repo")


def test_closing_the_umbrella_item_closes_the_note_and_keeps_the_body(
    fake: FakeTodoMcp, client: TodoClient
) -> None:
    note = _seed(fake)
    before = fake.store.notes[note].text
    client.close_item(split_items(client.get_task(note[:8]))[0], "all shipped")
    stored = fake.store.notes[note]
    assert (stored.status, stored.evidence) == ("done", "all shipped")
    assert stored.text == before
    assert [c[0] for c in fake.calls].count("update_task") == 0


def test_a_repo_note_with_the_marker_works_too(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "kuhyx/todoImplementer")
    (item,) = split_items(client.get_task(note[:8]))
    assert item.repo == "kuhyx/todoImplementer"


def test_tick_child_rewrites_the_header_checkbox(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake)
    client.tick_child(note[:8], "bbbb2222-0")
    text = fake.store.notes[note].text
    assert "- [x] kuhyx/beta (bbbb2222)" in text
    assert "- [ ] kuhyx/alpha (aaaa1111)" in text
    client.tick_child(note[:8], "bbbb2222-0")
    assert [c[0] for c in fake.calls].count("update_task") == 1
