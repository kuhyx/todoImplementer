"""A part's own section text, rewritten in its note: checked by reading the result back (856c0f0a)."""

from __future__ import annotations

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import TodoClient, TodoError
from todoimpl.todo_mcp.edit import EditError, rewrite_section, whole_note
from todoimpl.todo_mcp.items import split_items

BODY = "pre\n\n## a\nx\n\n## b\ny\nz\n\n## c\nw"


def test_rewrite_keeps_every_other_section_and_the_gap_before_the_next() -> None:
    assert rewrite_section(BODY, 1, "B new", "one\ntwo") == "pre\n\n## a\nx\n\n## B new\none\ntwo\n\n## c\nw"


def test_rewrite_of_the_last_section_and_an_empty_text() -> None:
    assert rewrite_section(BODY, 2, "c2", "") == "pre\n\n## a\nx\n\n## b\ny\nz\n\n## c2"


def test_a_fenced_heading_in_the_new_text_is_fine() -> None:
    assert "## b\n```\n## not one\n```" in rewrite_section(BODY, 1, "b", "```\n## not one\n```")


@pytest.mark.parametrize(
    ("title", "text"),
    [
        ("b", "line\n## sneaky new section"),  # a heading would split the part in two
        ("b", "```\nopen fence swallows c"),  # an unclosed fence hides every later section
        ("[x] b", "y"),  # a done marker would close the part unshipped
        ("#b", "y"),  # `## #b` is no heading: the section would vanish
        ("b\nc", "y"),  # a title is one line
    ],
)
def test_rewrite_refuses_text_that_reads_back_as_another_note(title: str, text: str) -> None:
    with pytest.raises(EditError):
        rewrite_section(BODY, 1, title, text)


def test_whole_note_text_must_stay_without_sections() -> None:
    assert whole_note("plain\ntext") == "plain\ntext"
    with pytest.raises(EditError):
        whole_note("x\n## now a section")


def test_whole_note_must_not_become_an_umbrella() -> None:
    with pytest.raises(EditError):
        whole_note("Umbrella: per-repo\n")


def _seed(fake: FakeTodoMcp, body: str) -> str:
    return fake.seed("kuhyx/r", "r todos", body)


def test_edit_section_writes_only_that_section(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\nx\n\n## b\ny")
    item = split_items(client.get_task(note[:8]))[1]
    client.edit_section(item, "b2", "new y")
    assert fake.store.notes[note].text == "r todos\n\n## a\nx\n\n## b2\nnew y"


def test_edit_of_a_note_without_sections_sets_its_title_and_body(
    fake: FakeTodoMcp, client: TodoClient
) -> None:
    note = _seed(fake, "old text")
    client.edit_section(split_items(client.get_task(note[:8]))[0], "new title", "new text")
    stored = client.get_task(note[:8])
    assert (stored.title, stored.body) == ("new title", "new text")


def test_edit_fails_closed_on_a_section_that_moved(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\nx\n\n## b\ny")
    item = split_items(client.get_task(note[:8]))[1]
    client.update_task(note[:8], body="## b\ny")  # someone dropped section a meanwhile
    with pytest.raises(TodoError, match="moved"):
        client.edit_section(item, "b2", "z")
    assert fake.store.notes[note].text == "r todos\n\n## b\ny"


def test_edit_fails_closed_on_a_section_ticked_meanwhile(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "## a\nx\n\n## b\ny")
    item = split_items(client.get_task(note[:8]))[0]
    client.close_item(item, "sha exit 0")
    with pytest.raises(TodoError, match="moved"):
        client.edit_section(item, "a2", "z")


def test_edit_fails_closed_on_a_retitled_note(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "text")
    item = split_items(client.get_task(note[:8]))[0]
    client.update_task(note[:8], title="other")
    with pytest.raises(TodoError, match="moved"):
        client.edit_section(item, "t", "z")


def test_edit_refuses_an_umbrella_note(fake: FakeTodoMcp, client: TodoClient) -> None:
    note = _seed(fake, "Umbrella: per-repo\n\n## kuhyx/a\nx")
    with pytest.raises(TodoError, match="umbrella"):
        client.edit_section(split_items(client.get_task(note[:8]))[0], "t", "z")
