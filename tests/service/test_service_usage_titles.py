"""/api/usage names every run dir by the best title there is, never the bare id (T1996)."""

from pathlib import Path

import pytest
from fake_todo_mcp import FakeTodoMcp
from servicefakes import Rig, write_stream
from todoimpl.board.state import run_dir
from todoimpl.service.runtitles import RunTitles, best_title
from todoimpl.todo_mcp.client import TodoClient


def _titles(rig: Rig) -> dict[str, str]:
    return {t["id"]: t["title"] for t in rig.backend.usage()["cost"]["per_task"]}


def test_t1996_a_part_of_an_open_repo_card_is_named_by_its_part_title(rig: Rig) -> None:
    rig.note(body="## First part\nbody one\n\n## Second part\nbody two")
    note = next(iter(rig.fake.store.notes))[:8]
    write_stream(run_dir(rig.root, f"{note}-1"), [])
    assert _titles(rig) == {f"{note}-1": "Second part"}


def test_t1996_a_run_of_a_closed_note_is_named_from_the_note_itself(rig: Rig, fake: FakeTodoMcp) -> None:
    note = fake.seed("kuhyx/demo", "demo todos", "## Gone one\nx\n\n## Gone two\ny", status="done")
    rig.run(f"{note[:8]}-1", "failed")
    write_stream(run_dir(rig.root, f"{note[:8]}-1"), [])
    rig.backend.cache.refresh()
    assert _titles(rig) == {f"{note[:8]}-1": "Gone two"}


def test_t1996_a_note_without_that_section_falls_back_to_the_note_title(rig: Rig, fake: FakeTodoMcp) -> None:
    note = fake.seed("kuhyx/demo", "Whole note", "", status="done")
    write_stream(run_dir(rig.root, f"{note[:8]}-4"), [])
    rig.backend.cache.refresh()
    assert _titles(rig) == {f"{note[:8]}-4": "Whole note"}


def test_t1996_a_label_heading_is_not_a_title(rig: Rig) -> None:
    body = "## What\nWhen a task passes its check, the board starts it. More text.\n\n## Other\nz"
    ids = rig.sections(body)
    write_stream(run_dir(rig.root, ids[0]), [])
    assert _titles(rig) == {ids[0]: "When a task passes its check, the board starts it."}


@pytest.mark.parametrize(
    ("title", "body", "want"),
    [
        ("What", "", "What"),  # nothing else is known
        ("why", "Because it is slow. And so on.", "Because it is slow."),
        ("Real title", "Body.", "Real title"),
        ("Goal", "x" * 200, "x" * 79 + "…"),
    ],
)
def test_best_title(title: str, body: str, want: str) -> None:
    assert best_title(title, body) == want


def test_unreachable_notes_are_retried_later_not_every_round(fake: FakeTodoMcp, tmp_path: Path) -> None:
    (tmp_path / "cafe0123-0").mkdir()
    now = [0.0]
    book = RunTitles(TodoClient(fake.url, fake.token), tmp_path, clock=lambda: now[0])
    book.update(set())
    book.update(set())
    assert sum(1 for name, _ in fake.calls if name == "get_task") == 1
    now[0] = 10_000.0
    book.update(set())
    assert sum(1 for name, _ in fake.calls if name == "get_task") == 2
    assert book.titles() == {}


def test_a_missing_run_root_asks_for_nothing(fake: FakeTodoMcp, tmp_path: Path) -> None:
    book = RunTitles(TodoClient(fake.url, fake.token), tmp_path / "none")
    book.update(set())
    assert fake.calls == []
