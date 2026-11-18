"""POST /api/sessions/handoff refusals and failures: all-or-nothing up to the first task, partial after it."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
import sessfix as fx
from handofffix import SIDS, FakeBoard, board, git, marks
from todoimpl.http.backend import BackendError
from todoimpl.sessions import api, handoff

if TYPE_CHECKING:
    from pathlib import Path

    from sessrunner import FakeRunner

__all__ = ["board", "git"]  # fixtures, imported for pytest


@pytest.mark.parametrize(
    "body",
    [
        {"ids": SIDS},  # six: over the cap
        {"ids": [SIDS[0], "nope"]},
        {"id": "00000000-0000-4000-8000-000000000000"},
    ],
)
def test_refusals_create_nothing(git: FakeRunner, board: FakeBoard, body: dict[str, object]) -> None:
    result = handoff.apply(git, body, board)
    assert result.refused is True
    assert (board.created, marks()) == ([], {})


def test_one_unmovable_session_refuses_the_whole_batch(
    git: FakeRunner, board: FakeBoard, sysroot: Path
) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session("A: approve"), sid=SIDS[2])
    api.SCANNER.forget({SIDS[2]})
    result = handoff.apply(git, {"ids": SIDS[:3]}, board)
    assert result.refused is True
    assert SIDS[2][:8] in result.summary
    assert "waits for your action" in result.summary
    assert (board.created, marks()) == ([], {})


def test_home_needs_a_repo_override_which_must_be_cloned(git: FakeRunner, board: FakeBoard) -> None:
    refused = handoff.apply(git, {"id": fx.OTHER_SID}, board)
    assert refused.refused is True
    assert "no GitHub origin" in refused.summary
    bad = handoff.apply(git, {"id": fx.OTHER_SID, "repos": {fx.OTHER_SID: "kuhyx/absent"}}, board)
    assert bad.refused is True
    assert "no clone of kuhyx/absent" in bad.summary
    moved = handoff.apply(git, {"id": fx.OTHER_SID, "repos": {fx.OTHER_SID: "kuhyx/other"}}, board)
    assert moved.ok, moved
    assert board.created[0].repo == "kuhyx/other"


@pytest.mark.parametrize(
    "repos",
    [["kuhyx/other"], {fx.OTHER_SID: 3}, {SIDS[0]: "kuhyx/other"}],
    ids=["not-a-map", "not-a-string", "id-not-asked"],
)
def test_a_malformed_repos_map_is_a_failure(git: FakeRunner, board: FakeBoard, repos: object) -> None:
    result = handoff.apply(git, {"id": fx.OTHER_SID, "repos": repos}, board)
    assert (result.ok, result.refused) == (False, False)
    assert board.created == []


def test_a_title_already_open_on_the_board_refuses_before_anything_is_created(
    git: FakeRunner, board: FakeBoard
) -> None:
    board.twins.add(("kuhyx/demo", "Task 1"))
    result = handoff.apply(git, {"ids": SIDS[:2]}, board)
    assert result.refused is True
    assert "already has an open part" in result.summary
    assert board.created == []


def test_two_sessions_with_one_title_refuse_together(
    git: FakeRunner, board: FakeBoard, sysroot: Path
) -> None:
    fx.write(fx.projects_dir(sysroot), [*fx.session("halfway"), fx.ai_title("Task 0")], sid=SIDS[1])
    result = handoff.apply(git, {"ids": SIDS[:2]}, board)
    assert result.refused is True
    assert "same title" in result.summary
    assert board.created == []


def test_a_broken_todo_service_while_checking_is_a_failure(git: FakeRunner, board: FakeBoard) -> None:
    board.twin_error = BackendError("upstream_unavailable", "todo MCP is down")
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (result.ok, result.refused) == (False, False)
    assert "todo MCP is down" in result.stderr


def test_a_create_failing_mid_batch_marks_only_what_landed(git: FakeRunner, board: FakeBoard) -> None:
    board.fail_at = 1
    result = handoff.apply(git, {"ids": SIDS[:3]}, board)
    assert (result.ok, result.refused) == (False, False)
    assert "Moved 1 of 3" in result.summary
    assert "todo MCP is down" in result.stderr
    assert set(marks()) == {SIDS[0]}


def test_a_create_conflict_is_a_refusal(git: FakeRunner, board: FakeBoard) -> None:
    board.fail_at = 0
    board.fail = BackendError("conflict", "kuhyx/demo already has an open part titled 'Task 0'")
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert result.refused is True
    assert marks() == {}


def test_without_a_board_nothing_can_move(git: FakeRunner) -> None:
    result = handoff.apply(git, {"id": SIDS[0]}, None)
    assert (result.ok, result.refused) == (False, False)
    assert marks() == {}


def test_marks_that_cannot_be_written_are_a_failure(
    git: FakeRunner, board: FakeBoard, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(path: Path, data: dict[str, object]) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(handoff, "write_marks", broken)
    result = handoff.apply(git, {"id": SIDS[0]}, board)
    assert (result.ok, result.refused) == (False, False)
    assert "disk full" in result.stderr
    assert len(board.created) == 1
