"""One issue, one part: the todo app is asked before a ticket is made (`errors/twin.py`, T2570)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from errfakes import kartka_entry, rec
from loopfakes import World
from todoimpl.errors import twin
from todoimpl.errors.record import AppError, parse
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import sections
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from fake_todo_mcp import FakeTodoMcp

A, B = "kartka:aaaa000001", "kartka:bbbb000002"
REPO = "kuhyx/kartka"


def record(**over: object) -> AppError:
    found = parse(rec(**over))
    assert found is not None
    return found


def open_sections(world: World) -> list[str]:
    return [
        "\n".join(s.lines) for n in world.fake.store.notes.values() for s in sections(n.text) if not s.done
    ]


def test_one_issue_under_two_signatures_is_one_part(world: World) -> None:
    world.entries(kartka_entry("aaaa000001"), kartka_entry("bbbb000002"))
    world.reason = None
    world.tick()
    assert len(world.tools("add_task")) == 1
    (part,) = [text for text in open_sections(world) if "Error-Signature" in text]
    assert f"Error-Signature: {A}" in part
    assert f"Error-Signature: {B}" in part
    assert {k: v["state"] for k, v in world.ledger().items()} == {A: "ticket", B: "ticket"}


def test_each_signature_of_one_part_keeps_its_own_count(world: World) -> None:
    world.entries(kartka_entry("aaaa000001"), kartka_entry("bbbb000002"))
    world.reason = None
    world.tick()
    world.rig.backend.cache.refresh()
    world.entries(kartka_entry("aaaa000001"), kartka_entry("bbbb000002", count=9))
    world.tick()
    (part,) = [text for text in open_sections(world) if "Error-Signature" in text]
    lines = part.split("\n")
    assert lines[lines.index(f"Error-Signature: {A}") - 1].startswith("Seen: 2x")
    assert lines[lines.index(f"Error-Signature: {B}") - 1].startswith("Seen: 9x")


def test_another_message_is_another_issue(world: World) -> None:
    other = {"at": "2026-11-02T10:00:00Z", "error": "timeout", "kind": "updates.check"}
    world.entries(kartka_entry("aaaa000001"), kartka_entry("bbbb000002", sample=other))
    world.reason = None
    world.tick()
    assert len(world.tools("add_task")) == 2


def test_lookup_skips_closed_parts_and_keeps_the_first_issue(fake: FakeTodoMcp) -> None:
    body = f"Error: crash: boom\nError-Signature: {A}"
    fake.seed_sections(
        REPO, [("[x] old", body.replace("aaaa000001", "cccc000003")), ("one", body), ("two", body)]
    )
    client = TodoClient(fake.url, fake.token)
    found = twin.lookup(client, record(signature="cccc000003", message="boom"), "Error: crash: boom")
    assert found is not None
    assert (found.title, found.same) == ("one", False)
    assert twin.lookup(client, record(signature="dddd000004"), "Error: crash: other") is None


def test_append_puts_the_block_before_trailing_blank_lines() -> None:
    body = "## a\nx\n\n\n## b\ny"
    assert twin.append(body, 0, "a", ["", "z"]) == "## a\nx\n\nz\n\n\n## b\ny"


def test_append_to_a_note_with_no_sections_adds_at_the_end() -> None:
    assert twin.append("just text\n\n", 0, "note", ["", "z"]) == "just text\n\nz"


@pytest.mark.parametrize(("index", "title"), [(3, "a"), (0, "moved"), (1, "b")])
def test_append_refuses_a_moved_or_closed_part(index: int, title: str) -> None:
    with pytest.raises(TodoError):
        twin.append("## a\nx\n## [x] b\ny", index, title, ["z"])


def test_block_of_a_text_with_no_error_line_is_the_whole_text() -> None:
    assert twin.block("Seen: 1x\nError-Signature: a:b") == ["", "Seen: 1x", "Error-Signature: a:b"]
