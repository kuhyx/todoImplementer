"""The fold of twin parts (`errors/repair.py`, T2570): groups, a moved part, a todo error, a bridging part."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from todoimpl.errors import ledger, repair
from todoimpl.repotask.model import Part
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import sections

if TYPE_CHECKING:
    from pathlib import Path

    from fake_todo_mcp import FakeTodoMcp
    from todoimpl.service.cards import CardTask

REPO = "kuhyx/kartka"


def body(key: str, error: str = "crash: boom") -> str:
    return f"Fix it.\n\nError: {error}\nSeen: 1x, first a, last b\nError-Signature: kartka:{key}"


def part(note: str, index: int, title: str, text: str) -> Part:
    return Part(f"{note[:8]}-{index}", note, index, title, text, "medium", None, human=False, held=False)


@dataclass(frozen=True)
class Card:
    id: str
    status: str
    parts: tuple[Part, ...]


def card(*parts: Part, status: str = "todo") -> CardTask:
    return cast("CardTask", Card("abcd1234-0", status, parts))


def seeded(fake: FakeTodoMcp, *texts: tuple[str, str]) -> tuple[str, list[Part]]:
    note = fake.seed_sections(REPO, list(texts))
    return note, [part(note, i, title, text) for i, (title, text) in enumerate(texts)]


def opened(fake: FakeTodoMcp, note: str) -> list[str]:
    return [s.title for s in sections(fake.store.notes[note].text) if not s.done]


def test_groups_skip_parts_with_no_signature_and_join_through_a_bridge() -> None:
    mine = part("n1", 0, "kuhy's own", "do a thing")
    one = part("n1", 1, "one", body("a1"))
    two = part("n1", 2, "two", body("b2", "crash: other"))
    bridge = part("n1", 3, "bridge", body("a1") + "\n" + body("b2", "crash: other"))
    assert repair.groups([mine, one, two, bridge]) == [[one, bridge, two]]
    assert repair.groups([mine, one, two]) == []


def test_a_twin_under_another_signature_moves_its_block_then_closes(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    note, parts = seeded(fake, ("one", body("a1")), ("two", body("b2") + "\n" + body("c3")))
    ledger.put(tmp_path, "kartka:b2", state="ticket", title="two", count=1)
    ledger.put(tmp_path, "kartka:a1", state="fixed")
    assert repair.fold(tmp_path, [card(*parts)], TodoClient(fake.url, fake.token)) == 1
    assert opened(fake, note) == ["one"]
    (kept,) = [s for s in sections(fake.store.notes[note].text) if not s.done]
    assert "Error-Signature: kartka:b2" in kept.lines
    assert ledger.load(tmp_path)["kartka:b2"]["title"] == "one"
    assert "title" not in ledger.load(tmp_path)["kartka:a1"]
    assert "kartka:c3" not in ledger.load(tmp_path)  # no ticket of its own: nothing to rename


def test_a_moved_or_closed_part_is_left_alone(fake: FakeTodoMcp, tmp_path: Path) -> None:
    note, parts = seeded(fake, ("one", body("a1")), ("two", body("a1")))
    client = TodoClient(fake.url, fake.token)
    gone = part(note, 5, "two", body("a1"))
    renamed = part(note, 1, "renamed", body("a1"))
    assert repair.fold(tmp_path, [card(parts[0], gone)], client) == 0
    assert repair.fold(tmp_path, [card(parts[0], renamed)], client) == 0
    assert repair.fold(tmp_path, [card(renamed, parts[1])], client) == 0
    assert opened(fake, note) == ["one", "two"]


def test_closed_cards_and_cards_with_no_twins_are_skipped(fake: FakeTodoMcp, tmp_path: Path) -> None:
    note, parts = seeded(fake, ("one", body("a1")), ("two", body("a1")))
    client = TodoClient(fake.url, fake.token)
    assert repair.fold(tmp_path, [card(*parts, status="done"), card(parts[0])], client) == 0
    assert opened(fake, note) == ["one", "two"]


def test_a_todo_error_leaves_the_twins_for_the_next_tick(fake: FakeTodoMcp, tmp_path: Path) -> None:
    note, parts = seeded(fake, ("one", body("a1")), ("two", body("a1")))
    fake.force_text("get_task", "boom", is_error=True)
    assert repair.fold(tmp_path, [card(*parts)], TodoClient(fake.url, fake.token)) == 0
    assert opened(fake, note) == ["one", "two"]
