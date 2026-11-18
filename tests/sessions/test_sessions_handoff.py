"""POST /api/sessions/handoff: a stalled session becomes a board task, its card starts, the row leaves."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
import sessfix as fx
from handofffix import SIDS, FakeBoard, board, git, marks
from todoimpl.sessions import api, handoff, handoff_text, router
from todoimpl.todo_mcp.items import sections

if TYPE_CHECKING:
    from pathlib import Path

    from sessrunner import FakeRunner

__all__ = ["board", "git"]  # fixtures, imported for pytest


def test_one_session_becomes_a_started_card_and_is_marked_done(git: FakeRunner, board: FakeBoard) -> None:
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (result.ok, result.refused) == (True, False), result
    task = board.created[0]
    assert (task.repo, task.title, task.images, task.files) == ("kuhyx/demo", "Task 0", (), ())
    assert board.started == ["note0001-0"]
    assert set(marks()) == {SIDS[0]}
    assert "note0001" in result.summary
    assert "note0001-0" in result.summary
    assert f"{SIDS[0]}: note note0001 card note0001-0 started" in result.stdout


def test_the_body_names_the_transcript_and_keeps_the_user_text_inert(
    git: FakeRunner, board: FakeBoard, sysroot: Path
) -> None:
    handoff.apply(git, {"id": SIDS[0]}, board)
    body = board.created[0].body
    for heading in ("### what", "### where", "### done", "### verify", "### read first"):
        assert heading in body
    transcript = fx.projects_dir(sysroot) / "-home-tester-src-demo" / f"{SIDS[0]}.jsonl"
    assert str(transcript) in body
    assert fx.CWD in body
    assert "last reply:" in body
    assert "> halfway 0" in body
    assert "> ## not a heading" in body
    assert "CLAUDE.md" in body
    # Appended under its `## <title>` heading, the task stays one section with no done_check of its own.
    found = sections(f"## {board.created[0].title}\n{body}")
    assert len(found) == 1
    assert not any(line.strip().startswith(("done_check:", "```")) for line in found[0].lines)


def test_bulk_moves_every_session_in_one_go(git: FakeRunner, board: FakeBoard) -> None:
    result = handoff.apply(git, {"ids": SIDS[:3]}, board)
    assert result.ok, result
    assert [t.title for t in board.created] == ["Task 0", "Task 1", "Task 2"]
    assert len(board.started) == 3
    assert set(marks()) == set(SIDS[:3])
    assert result.summary == "Moved 3 sessions to the board."


def test_a_card_that_cannot_start_now_still_counts_as_moved(git: FakeRunner, board: FakeBoard) -> None:
    board.start_ok = False
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert result.ok
    assert "not started" in result.stdout
    assert set(marks()) == {SIDS[0]}


def test_a_non_object_body_is_a_failure(git: FakeRunner, board: FakeBoard) -> None:
    assert handoff.apply(git, ["x"], board).ok is False


def test_the_router_knows_handoff_and_passes_the_board(git: FakeRunner, board: FakeBoard) -> None:
    payload = router.mutate(git, "handoff", {"id": SIDS[0]}, board)
    assert payload is not None
    assert payload["ok"] is True
    assert router.mutate(git, "resume", {"id": "nope"}) is not None


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("  Fix\nthe   header ", "Fix the header"),
        ("[x] looks done", "looks done"),
        ("   ", "Session 11111111"),
        ("y" * 300, "y" * 199 + "…"),
    ],
)
def test_the_task_title_is_one_safe_line(git: FakeRunner, raw: str, expected: str) -> None:
    session = api.find(SIDS[0])
    assert session is not None
    assert handoff_text.title(replace(session, title=raw)) == expected
