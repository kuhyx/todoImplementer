"""A handoff is idempotent: a rerun adopts the task an earlier, half-finished run created (T2047)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from handofffix import SIDS, FakeBoard, board, git, marks
from todoimpl.sessions import handoff

if TYPE_CHECKING:
    from sessrunner import FakeRunner

__all__ = ["board", "git"]  # fixtures, imported for pytest


def test_t2047_a_rerun_adopts_the_task_that_landed_and_marks_the_session_done(
    git: FakeRunner, board: FakeBoard
) -> None:
    board.adoptable[("kuhyx/demo", "Task 0", SIDS[0])] = ("noteaaaa", "noteaaaa-0")
    result = handoff.apply(git, {"ids": SIDS[:2]}, board)
    assert (result.ok, result.refused) == (True, False), result
    assert [t.title for t in board.created] == ["Task 1"]  # no twin of Task 0
    assert board.started == ["noteaaaa-0", "note0001-0"]
    assert set(marks()) == {SIDS[0], SIDS[1]}
    assert f"{SIDS[0]}: note noteaaaa card noteaaaa-0 started" in result.stdout


def test_a_twin_of_someone_elses_part_is_still_refused(git: FakeRunner, board: FakeBoard) -> None:
    board.adoptable[("kuhyx/demo", "Task 0", "another session")] = ("noteaaaa", "noteaaaa-0")
    board.twins.add(("kuhyx/demo", "Task 0"))
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert result.refused is True
    assert (board.created, board.started, marks()) == ([], [], {})


def test_a_card_that_never_shows_leaves_its_session_for_a_rerun(git: FakeRunner, board: FakeBoard) -> None:
    board.hidden.add("note0002")
    result = handoff.apply(git, {"ids": SIDS[:3]}, board)
    assert (result.ok, result.refused) == (False, False)
    assert "Moved 2 of 3" in result.summary
    assert "note0002" in result.stderr
    assert set(marks()) == {SIDS[0], SIDS[2]}
    assert board.started == ["note0001-0", "note0003-0"]


def test_t2047_rerunning_a_half_finished_handoff_finishes_it(git: FakeRunner, board: FakeBoard) -> None:
    board.hidden.add("note0001")
    first = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (first.ok, marks()) == (False, {})
    board.hidden.clear()
    second = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (second.ok, second.refused) == (True, False), second
    assert len(board.created) == 1  # no twin
    assert board.started == ["note0001-0"]
    assert set(marks()) == {SIDS[0]}


def test_a_failing_card_lookup_names_why_and_leaves_the_session_for_a_rerun(
    git: FakeRunner, board: FakeBoard
) -> None:
    board.broken.add("note0001")
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (result.ok, marks()) == (False, {})
    assert "todo MCP is down" in result.stderr
