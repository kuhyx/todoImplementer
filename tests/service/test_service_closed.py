"""Shipped cards stay on the board after their note is closed (T103); closed notes are fetched once."""

import logging

import pytest
from fake_todo_mcp import FakeTodoMcp
from servicefakes import Rig


def _closed_shipped(rig: Rig, fake: FakeTodoMcp, *, stage: str = "shipped") -> str:
    card = rig.note()
    rig.run(card, stage)
    fake.store.notes[next(iter(fake.store.notes))].status = "done"
    rig.backend.cache.refresh()
    return card


def test_t103_shipped_card_survives_its_note_being_closed(rig: Rig, fake: FakeTodoMcp) -> None:
    card = _closed_shipped(rig, fake)
    assert rig.card(card)["column"] == "done"


def test_closed_note_is_fetched_once_not_every_refresh(rig: Rig, fake: FakeTodoMcp) -> None:
    _closed_shipped(rig, fake)
    before = sum(1 for name, _ in fake.calls if name == "get_task")
    rig.backend.cache.refresh()
    rig.backend.cache.refresh()
    assert sum(1 for name, _ in fake.calls if name == "get_task") == before


def test_closed_note_without_a_shipped_run_stays_off_the_board(rig: Rig, fake: FakeTodoMcp) -> None:
    card = _closed_shipped(rig, fake, stage="implement")
    assert [c for c in rig.backend.board()["tasks"] if c["id"] == card] == []


def test_unreadable_state_and_stray_dirs_are_skipped(rig: Rig, fake: FakeTodoMcp) -> None:
    (rig.root / "stray").mkdir(parents=True)
    (rig.root / "file.txt").write_text("x", encoding="utf-8")
    (rig.root / "deadbeef-0").mkdir()
    (rig.root / "deadbeef-0" / "state.json").write_text("{not json", encoding="utf-8")
    card = _closed_shipped(rig, fake)
    assert rig.card(card)["column"] == "done"


def test_a_failing_get_task_for_a_closed_note_does_not_blank_the_board(
    rig: Rig, fake: FakeTodoMcp, caplog: pytest.LogCaptureFixture
) -> None:
    open_card = rig.note("open todos")
    rig.run("cafe0123-0", "shipped")
    caplog.set_level(logging.WARNING, logger="todoimpl.service")
    rig.backend.cache.refresh()
    snap = rig.backend.cache.snapshot()
    assert snap.error is None
    assert [t.id for t in snap.tasks] == [open_card]
    assert "cafe0123" in caplog.text


def test_missing_run_root_adds_nothing(rig: Rig) -> None:
    assert not rig.root.exists()
    rig.note()
    assert len(rig.backend.cache.snapshot().tasks) == 1
