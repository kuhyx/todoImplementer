"""The errors loop: one ticket per error, the gated start, the count and the twin."""

from __future__ import annotations

import pytest
from errfakes import kartka_entry, write_kartka
from loopfakes import CARD, KEY, World
from todoimpl.board.state import run_dir
from todoimpl.errors import ledger
from todoimpl.errors.sources import Source
from todoimpl.http.backend import BackendError
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.scheduler import RunnerError


def test_t2009_one_open_error_becomes_one_ticket_and_starts_the_card(world: World) -> None:
    world.entries(kartka_entry())
    world.tick()
    (added,) = world.tools("add_task")
    assert added["repo"] == "kuhyx/kartka"
    assert added["title"].startswith("Fix kartka: updates.check SuwayomiException: x")
    assert f"Error-Signature: {KEY}" in added["body"]
    assert world.starts() == [("start", CARD, True)]
    extra = world.sched.extras[0]
    assert extra is not None
    assert extra["app_error"]["keys"] == [KEY]
    assert extra["app_error"]["reason"] == "weekly"
    entry = world.ledger()[KEY]
    assert (entry["state"], entry["count"], entry["starts"]) == ("ticket", 2, 1)


def test_t2010_the_same_error_never_makes_a_second_ticket(world: World) -> None:
    world.entries(kartka_entry())
    for _ in range(4):
        world.tick()
    assert len(world.tools("add_task")) == 1
    assert len(world.starts()) == 1  # the card now works: no second start


def test_t2010_a_lost_ledger_finds_the_ticket_by_its_signature_line(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    (world.rig.root / ledger.FILE).unlink()
    world.tick()
    assert len(world.tools("add_task")) == 1
    assert world.ledger()[KEY]["state"] == "ticket"


def test_t2011_a_card_made_while_usage_is_high_starts_when_the_gate_opens(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    world.tick()
    assert world.starts() == []
    assert len(world.tools("add_task")) == 1
    world.reason = "credits"  # the weekly reset, or free credits again
    world.tick()
    assert len(world.starts()) == 1
    assert world.sched.extras[0]["app_error"]["reason"] == "credits"  # type: ignore[index]


def test_t2012_at_most_one_card_starts_per_tick(world: World) -> None:
    world.entries(kartka_entry("aaa"), kartka_entry("bbb"))
    other = Source("tutor", "kuhyx/tutor", "kartka", world.tmp / "tutor.json")
    write_kartka(other.path, kartka_entry("ccc"))
    world.loop.sources = lambda: [world.source, other]
    world.tick()
    assert len(world.starts()) == 1  # kartka's two errors are one card, tutor's is another
    world.tick()
    assert len(world.starts()) == 2
    assert {c[1] for c in world.starts()} == {CARD, repo_card_id("kuhyx/tutor")}


def test_t2013_t2445_a_started_ticket_is_never_marked_cheap(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = "credits"
    world.tick()
    assert "Tier: cheap" not in world.note_text()
    assert world.sched.extras[0]["app_error"]["reason"] == "credits"  # type: ignore[index]


def test_t2014_a_card_at_work_or_failed_is_not_started_again(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    world.reason = "weekly"
    for stage in ("implement", "failed", "gate", "cancelled"):
        world.run(stage)
        world.tick()
    assert world.starts() == []


def test_t2014_a_shipped_card_with_a_part_left_starts_its_next_cycle(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    world.reason = "weekly"
    world.run("shipped")
    world.tick()
    assert len(world.starts()) == 1
    assert world.ledger()[KEY]["starts"] == 1


def test_t2015_a_part_is_started_at_most_three_times(world: World) -> None:
    world.entries(kartka_entry())
    world.tick()
    for _ in range(5):
        world.run("shipped")
        world.tick()
    assert len(world.starts()) == 3


def test_a_refused_start_is_not_counted_and_not_fatal(world: World) -> None:
    world.entries(kartka_entry())
    world.sched.refuse = RunnerError("busy", "conflict")
    world.tick()
    assert world.ledger()[KEY]["starts"] == 0
    world.sched.refuse = None
    world.tick()
    assert world.ledger()[KEY]["starts"] == 1


def test_t2016_a_changed_count_updates_the_note_once(world: World) -> None:
    world.entries(kartka_entry(count=2))
    world.tick()
    world.entries(kartka_entry(count=9, last="2026-11-09T00:00:00Z"))
    world.tick()
    (update,) = world.tools("update_task")
    assert "Seen: 9x, first 2026-11-01T10:00:00Z, last 2026-11-09T00:00:00Z" in update["body"]
    world.tick()
    assert len(world.tools("update_task")) == 1  # unchanged: no write
    assert world.ledger()[KEY]["count"] == 9


def test_a_resolved_record_makes_no_ticket(world: World) -> None:
    world.entries(kartka_entry(resolved="2026-11-03T00:00:00Z"))
    world.tick()
    assert world.tools("add_task") == []


def test_a_broken_source_is_skipped_and_the_loop_goes_on(world: World) -> None:
    world.state.write_text("nope", encoding="utf-8")
    world.tick()
    assert world.tools("add_task") == []


def test_a_refused_twin_title_is_left_alone(world: World, monkeypatch: pytest.MonkeyPatch) -> None:
    world.entries(kartka_entry())

    def refuse(_task: object) -> tuple[str, str]:
        raise BackendError("conflict", "already open")

    monkeypatch.setattr(world.rig.backend.new_task_service, "create", refuse)
    world.tick()
    assert world.ledger() == {}


def test_a_part_that_vanishes_for_two_ticks_is_forgotten_and_made_again(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    for note in world.fake.store.notes.values():
        note.text = "## Something else\ntext"
    world.rig.backend.cache.refresh()
    world.tick()
    assert world.ledger()[KEY]["missing"] == 1  # a ship may be closing it right now: wait one tick
    assert len(world.tools("add_task")) == 1
    world.tick()
    assert len(world.tools("add_task")) == 2
    assert world.ledger()[KEY]["state"] == "ticket"


def test_a_part_that_comes_back_before_the_second_tick_resets_its_missing_count(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    (note,) = world.fake.store.notes.values()
    kept = note.text
    note.text = "## Something else\ntext"
    world.rig.backend.cache.refresh()
    world.tick()
    assert world.ledger()[KEY]["missing"] == 1
    note.text = kept
    world.rig.backend.cache.refresh()
    world.tick()
    assert world.ledger()[KEY]["missing"] == 0
    assert len(world.tools("add_task")) == 1


def test_a_count_that_cannot_be_written_is_tried_again_next_tick(world: World) -> None:
    world.entries(kartka_entry(count=2))
    world.reason = None
    world.tick()
    world.entries(kartka_entry(count=9))
    world.fake.force_text("update_task", "boom", is_error=True)
    world.tick()
    assert world.ledger()[KEY]["count"] == 2
    world.tick()
    assert world.ledger()[KEY]["count"] == 9


def test_a_card_with_an_unreadable_run_is_left_alone(world: World) -> None:
    world.entries(kartka_entry())
    world.reason = None
    world.tick()
    path = run_dir(world.rig.root, CARD)
    path.mkdir(parents=True, exist_ok=True)
    (path / "state.json").write_text("{not json", encoding="utf-8")
    world.reason = "weekly"
    world.tick()
    assert world.starts() == []
