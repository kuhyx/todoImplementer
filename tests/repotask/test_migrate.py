"""One todo note per repo: the migration merges a repo's open notes, dry run first (T1914)."""

from __future__ import annotations

import runpy
import sys
from typing import TYPE_CHECKING

import pytest
from fake_todo_mcp import FakeTodoMcp
from todoimpl.board.state import RunState, save
from todoimpl.repotask import migrate
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.todo_mcp.model import TodoError

if TYPE_CHECKING:
    from pathlib import Path

WRITES = {"update_task", "close_task", "add_task"}


def client(fake: FakeTodoMcp) -> TodoClient:
    return TodoClient(fake.url, fake.token)


def full(fake: FakeTodoMcp, note: str) -> str:
    return next(key for key in fake.store.notes if key.startswith(note))


def seed_repo(fake: FakeTodoMcp) -> tuple[str, str, str]:
    """Three notes of kuhyx/r: two sections; no sections with a check; one section with a note-level check."""
    first = fake.seed("kuhyx/r", "r todos", "## a\nalpha\n\n## b\nbeta", id="aaaa1111-0000")
    second = fake.seed("kuhyx/r", "Plain note", "gamma", id="bbbb2222-0000", done_check="make gamma")
    third = fake.seed("kuhyx/r", "single", "## only\ndelta", id="cccc3333-0000", done_check="make delta",
                      priority="high")  # fmt: skip
    fake.seed("kuhyx/other", "alone", "## x\ny", id="dddd4444-0000")
    fake.seed("kuhyx/r", "umbrella", "Umbrella: per-repo\n## kuhyx/a (aaaa1111)\ntext", id="ffff6666-0000")
    fake.seed(None, "no repo", "## x\ny", id="eeee5555-0000")
    return first[:8], second[:8], third[:8]


def test_t1915_a_dry_run_reports_the_merge_and_writes_nothing(
    fake: FakeTodoMcp, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second, third = seed_repo(fake)
    before = {key: note.text for key, note in fake.store.notes.items()}
    assert migrate.main(["--root", str(tmp_path)], client(fake)) == 0
    out = capsys.readouterr().out
    assert f"kuhyx/r: into {first} <- {third}, {second}" in out
    assert "repos with more than one note: 1; notes would merge: 2; skipped (run in flight): 0" in out
    assert not [name for name, _ in fake.calls if name in WRITES]
    assert {key: note.text for key, note in fake.store.notes.items()} == before


def test_t1915_apply_moves_the_sections_into_one_note_and_closes_the_rest(
    fake: FakeTodoMcp, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    first, second, third = seed_repo(fake)
    assert migrate.main(["--apply", "--root", str(tmp_path)], client(fake)) == 0
    assert "notes merged: 2" in capsys.readouterr().out
    target = fake.store.notes[full(fake, first)]
    assert (target.status, target.priority) == ("todo", "high")
    for text in ("## a\nalpha", "## b\nbeta", "## Plain note", "gamma", "## only", "delta"):
        assert text in target.text
    assert "done_check: make gamma" in target.text
    assert "done_check: make delta" in target.text
    for source in (second, third):
        closed = fake.store.notes[full(fake, source)]
        assert (closed.status, closed.evidence) == ("done", f"merged into {first}")
    assert fake.store.notes[full(fake, "dddd4444")].status == "todo"
    assert (
        migrate.main(["--apply", "--root", str(tmp_path)], client(fake)) == 0
    )  # a second run has nothing to do
    assert "repos with more than one note: 0" in capsys.readouterr().out


def test_a_note_with_an_older_run_in_flight_is_skipped_and_the_busy_note_is_the_target(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    first, second, third = seed_repo(fake)
    save(tmp_path / f"{second}-0", RunState(task_id=f"{second}-0", stage="gate"))
    save(tmp_path / f"{third}-0", RunState(task_id=f"{third}-0", stage="shipped"))
    found = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    (one,) = found
    assert (one.target, one.sources, one.skipped) == (second, [first, third], {})
    save(tmp_path / f"{first}-1", RunState(task_id=f"{first}-1", stage="gate"))
    (again,) = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    assert again.target in (first, second)
    assert list(again.skipped.values()) == ["an older run is still in flight"]
    assert third in again.sources


def test_a_target_without_sections_is_wrapped_and_a_single_section_keeps_its_note_level_check(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    a = fake.seed("kuhyx/r", "First", "plain one", id="aaaa1111-0000", done_check="make one")
    b = fake.seed("kuhyx/r", "Second", "## s\nplain two", id="bbbb2222-0000", done_check="make two")
    c = fake.seed(
        "kuhyx/r", "Third", "## t\nplain three\ndone_check: make own", id="cccc3333-0000", done_check="x"
    )
    notes = migrate.open_notes(client(fake))
    (one,) = migrate.plan(notes, tmp_path)
    assert one.target == b[:8]  # the note that already has a section keeps its ids
    migrate.move(client(fake), one, a[:8])
    migrate.move(client(fake), one, c[:8])
    text = fake.store.notes[b].text
    assert "## s\ndone_check: make two\nplain two" in text
    assert "## First\ndone_check: make one\nplain one" in text
    assert "done_check: make own" in text
    assert "done_check: x" not in text


def test_a_whole_note_target_becomes_section_zero(fake: FakeTodoMcp, tmp_path: Path) -> None:
    a = fake.seed("kuhyx/r", "First", "plain one", id="aaaa1111-0000", done_check="make one")
    b = fake.seed("kuhyx/r", "Second", "plain two", id="bbbb2222-0000")
    (one,) = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    assert (one.target, one.sources) == (a[:8], [b[:8]])
    assert migrate.move(client(fake), one, b[:8]) == 1
    assert (
        fake.store.notes[a].text.split("\n\n", 1)[1].startswith("## First\ndone_check: make one\nplain one")
    )


def test_text_before_the_first_section_and_manual_titles_survive_the_move(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    a = fake.seed("kuhyx/r", "Base", "## one\nx\n\n## two\ny", id="aaaa1111-0000")
    b = fake.seed(
        "kuhyx/r", "Mixed", "Context line.\n\n## [x] done one\nclosed: ok\n\n## live\nz", id="bbbb2222-0000"
    )
    c = fake.seed("kuhyx/r", "MANUAL WORK REQUIRED: rotate", "by hand", id="cccc3333-0000")
    (one,) = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    for source in one.sources:
        migrate.move(client(fake), one, source)
    text = fake.store.notes[a].text
    assert "## Mixed\nContext line." in text
    assert "## live\nz" in text
    assert "done one" not in text
    assert "## MANUAL WORK REQUIRED: rotate" in text
    assert fake.store.notes[b].status == fake.store.notes[c].status == "done"


def test_a_rerun_after_a_failure_between_the_write_and_the_close_adds_nothing_twice(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    first, second, _ = seed_repo(fake)
    (one,) = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    fake.force_text("close_task", "error: the todo app is down", is_error=True)
    with pytest.raises(TodoError, match="down"):
        migrate.move(client(fake), one, second)
    once = fake.store.notes[full(fake, first)].text
    assert migrate.move(client(fake), one, second) == 0
    assert fake.store.notes[full(fake, first)].text == once
    assert fake.store.notes[full(fake, second)].status == "done"


def test_nothing_is_closed_when_the_target_did_not_take_the_sections(
    fake: FakeTodoMcp, tmp_path: Path
) -> None:
    _, second, _ = seed_repo(fake)
    (one,) = migrate.plan(migrate.open_notes(client(fake)), tmp_path)
    todo = client(fake)
    todo.update_task = lambda id8, **_fields: todo.get_task(id8)  # type: ignore[method-assign]
    with pytest.raises(TodoError, match="did not take the sections"):
        migrate.move(todo, one, second)
    assert fake.store.notes[full(fake, second)].status == "todo"


def test_a_note_closed_while_listing_is_retried_then_reported(
    fake: FakeTodoMcp, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_repo(fake)
    todo = client(fake)
    real, calls = todo.list_tasks, []

    def flaky(*args: object, **kwargs: bool) -> list[object]:
        calls.append(1)
        if len(calls) < 3:
            raise TodoError("id: no live note")
        return real(*args, **kwargs)  # type: ignore[arg-type, return-value]

    todo.list_tasks = flaky  # type: ignore[method-assign, assignment]
    assert len(migrate.open_notes(todo)) == 5  # the repo-less note is not listed
    todo.list_tasks = lambda **_kw: (_ for _ in ()).throw(TodoError("gone"))  # type: ignore[method-assign]
    assert migrate.main(["--root", str(tmp_path)], todo) == 1
    assert "todo app: gone" in capsys.readouterr().err


def test_the_module_runs_with_the_environments_todo_app(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    seed_repo(fake)
    token = tmp_path / "token"
    token.write_text(fake.token, encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_MCP_URL", fake.url)
    monkeypatch.setenv("TODOIMPL_MCP_TOKEN_FILE", str(token))
    monkeypatch.setattr(sys, "argv", ["migrate", "--root", str(tmp_path / "runs")])
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.repotask.migrate", run_name="__main__")
    assert done.value.code == 0
    assert "notes would merge: 2" in capsys.readouterr().out
