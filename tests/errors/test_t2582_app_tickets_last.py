"""T2582: other apps' error tickets have the lowest priority and start by themselves only on an idle board.

kartka's card full of tickets started on its own while kuhy's cards waited. Now a card of only other apps'
reports starts by itself only when no other card is running or queued, its ticket is filed `low` (so it never
raises the priority kuhy gave the note), and the board's own tickets keep going first.
"""

from __future__ import annotations

from errfakes import kartka_entry, write_kartka
from loopfakes import CARD, World
from todoimpl.board.state import RunState, run_dir, save
from todoimpl.errors.sources import Source
from todoimpl.repotask.ids import repo_card_id
from todoimpl.stall import report

OTHER = repo_card_id("kuhyx/tutor")


def _busy(world: World, card: str, stage: str, error: str | None = None, last_tag: str | None = None) -> None:
    run = RunState(task_id=card, stage=stage, error=error, last_tag=last_tag)
    save(run_dir(world.rig.root, card), run)


def test_t2582_an_app_ticket_waits_while_another_card_runs(world: World) -> None:
    world.entries(kartka_entry())
    _busy(world, "abcd1234-0", "implement")
    world.tick()
    assert world.starts() == []
    _busy(world, "abcd1234-0", "shipped")
    world.tick()
    assert [c[1] for c in world.starts()] == [CARD]


def test_t2582_queued_and_paused_runs_count_needs_you_and_rest_do_not(world: World) -> None:
    world.entries(kartka_entry())
    for stage in ("paused_limit", "paused_retry", "plan", "gate"):
        _busy(world, "abcd1234-0", stage)
        world.tick()
    assert world.starts() == []
    _busy(world, "abcd1234-0", "implement", error="needs kuhy")
    world.tick()
    assert len(world.starts()) == 1


def test_t2582_a_run_waiting_on_kuhys_question_is_not_busy(world: World) -> None:
    world.entries(kartka_entry())
    _busy(world, "abcd1234-0", "implement", last_tag="Q")
    world.tick()
    assert len(world.starts()) == 1


def test_t2582_two_app_cards_start_one_after_the_other(world: World) -> None:
    world.entries(kartka_entry("aaa"))
    other = Source("tutor", "kuhyx/tutor", "kartka", world.tmp / "tutor.json")
    write_kartka(other.path, kartka_entry("ccc"))
    world.loop.sources = lambda: [world.source, other]
    world.tick()
    world.tick()
    assert len(world.starts()) == 1  # the first one runs: the second waits for an idle board
    _busy(world, world.starts()[0][1], "cancelled")
    world.tick()
    assert {c[1] for c in world.starts()} == {CARD, OTHER}


def test_t2582_the_ticket_is_filed_low(world: World) -> None:
    world.entries(kartka_entry())
    world.tick()
    (added,) = world.tools("add_task")
    assert added["priority"] == "low"


def test_t2582_a_board_ticket_starts_while_other_cards_run(world: World) -> None:
    report.file("parse-miss", "a turn's reply had no tag", 1000.0, kind="board.parse")
    world.loop.sources = lambda: [Source(report.APP, "", "contract", report.path())]
    _busy(world, "abcd1234-0", "implement")
    world.tick()
    assert [c[1] for c in world.starts()] == [repo_card_id(report.REPO)]
