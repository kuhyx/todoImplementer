"""A ticket merged into a combined note is still found by its signature line, never re-created (T2408)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from errfakes import kartka_entry
from loopfakes import KEY, World
from todoimpl.errors import ticket
from todoimpl.merge.apply import apply_merge
from todoimpl.merge.store import MergeStore
from todoimpl.service.repocards import section_cards
from todoimpl.todo_mcp.client import TodoClient

if TYPE_CHECKING:
    from todoimpl.service.cards import CardTask

OTHER = "Fix the same-looking thing in kartka"


def merge_ticket_with_another(world: World) -> None:
    """Add a second kartka section and merge the error ticket and it into one new card, as the board does."""
    cache = world.rig.backend.cache
    todo = TodoClient(world.fake.url, world.fake.token)
    todo.add_task("kuhyx/kartka", OTHER, "similar work")
    cache.refresh()
    members: list[CardTask] = [c for c in section_cards(list(cache.snapshot().tasks)) if c.repo]
    assert len(members) == 2
    apply_merge(todo, world.rig.root, MergeStore(world.rig.root), members, "Kartka fixes", lambda _t: "")
    cache.refresh()


def test_t2408_a_merged_ticket_is_still_found_by_its_signature(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    merge_ticket_with_another(world)
    cards = world.rig.backend.cache.snapshot().tasks
    found = ticket.find(cards, KEY)
    assert found is not None
    assert found.title == "Kartka fixes"
    assert f"Error-Signature: {KEY}" in found.text


def test_t2408_the_loop_does_not_recreate_a_merged_ticket(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    merge_ticket_with_another(world)
    world.tick()
    world.tick()
    fixes = [a for a in world.tools("add_task") if a["title"].startswith("Fix kartka: updates.check")]
    assert len(fixes) == 1
    assert world.ledger()[KEY]["state"] == "ticket"


def test_t2408_the_count_is_refreshed_inside_the_merged_note(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    merge_ticket_with_another(world)
    world.entries(kartka_entry(count=9))
    world.tick()
    assert "Seen: 9x" in world.note_text()
    assert "Seen: 2x" not in world.note_text()
