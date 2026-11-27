"""One signature, one open part: a blind board never makes a twin, and twins already made are folded (T2570).

Live case (2026-11-25 22:37): the server started while the todo MCP was down, the loop's first two ticks saw
no cards, `_missing` counted every open ticket as closed by hand and made each one again.
"""

from __future__ import annotations

from errfakes import kartka_entry
from loopfakes import CARD, KEY, World
from todoimpl.errors import ledger, ticket
from todoimpl.errors.loop import ErrorLoop
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.items import sections

TITLE = "Fix kartka: updates.check"


def open_parts(world: World, key: str = KEY) -> int:
    """Count the open sections of every note that carry `key`'s signature line."""
    line = f"Error-Signature: {key}"
    return sum(
        1 for n in world.fake.store.notes.values() for s in sections(n.text) if not s.done and line in s.lines
    )


def blind_loop(world: World) -> ErrorLoop:
    """Return the same loop right after a restart: the board's notes are not loaded yet, it shows no card."""
    return ErrorLoop(
        world.rig.root,
        cards=lambda: (),
        tasks=TodoClient(world.fake.url, world.fake.token),
        creator=world.rig.backend.new_task_service,  # type: ignore[arg-type]
        starter=world.rig.scheduler,
        gate=world.gate,
        sources=lambda: [world.source],
        clock=lambda: world.now,
    )


def fixes(world: World) -> int:
    return len([a for a in world.tools("add_task") if a["title"].startswith(TITLE)])


def test_t2570_two_blind_ticks_after_a_restart_make_no_second_part(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    blind = blind_loop(world)
    blind.tick()
    blind.tick()
    blind.tick()
    assert fixes(world) == 1
    assert open_parts(world) == 1
    assert world.ledger()[KEY]["state"] == "ticket"


def test_t2570_a_lost_ledger_on_a_blind_board_adopts_the_open_part(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    (world.rig.root / ledger.FILE).unlink()
    blind_loop(world).tick()
    assert fixes(world) == 1
    assert world.ledger()[KEY]["state"] == "ticket"


def test_t2570_the_todo_app_down_at_create_time_makes_nothing(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.fake.force_text("list_tasks", "boom", is_error=True)
    blind_loop(world).tick()
    assert world.ledger() == {}


def make_twin(world: World) -> None:
    """Make the live state: one ticket twice as open parts of the repo's note, the board showing both."""
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    found = ticket.find(world.rig.backend.cache.snapshot().tasks, KEY)
    assert found is not None
    TodoClient(world.fake.url, world.fake.token).add_task("kuhyx/kartka", found.title, found.text)
    world.rig.backend.cache.refresh()
    assert open_parts(world) == 2


def test_t2570_the_board_folds_twins_already_made_into_one_part(world: World) -> None:
    make_twin(world)
    world.entries(kartka_entry(count=7))
    world.tick()
    assert open_parts(world) == 1
    assert "closed: duplicate of" in world.note_text()
    world.rig.backend.cache.refresh()
    world.tick()
    assert "Seen: 7x" in "\n".join(
        "\n".join(s.lines) for n in world.fake.store.notes.values() for s in sections(n.text) if not s.done
    )


def test_t2570_the_repair_is_idempotent(world: World) -> None:
    make_twin(world)
    world.tick()
    world.rig.backend.cache.refresh()
    writes = len(world.tools("update_task"))
    world.tick()
    world.tick()
    assert len(world.tools("update_task")) == writes
    assert open_parts(world) == 1


def test_t2570_a_card_at_work_keeps_its_twins_until_it_rests(world: World) -> None:
    make_twin(world)
    world.run("implement")
    world.tick()
    assert open_parts(world) == 2
    world.run("cancelled")
    world.tick()
    assert open_parts(world) == 1
    assert CARD in {c.id for c in world.rig.backend.cache.snapshot().tasks}
