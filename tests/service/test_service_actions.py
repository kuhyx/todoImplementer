"""ServiceBackend actions: delegation, error mapping, lesson drafting on a gate rejection."""

import threading
from collections.abc import Callable
from typing import Any

import pytest
from servicefakes import Rig
from todoimpl.board.state import run_dir
from todoimpl.http.backend import BackendError
from todoimpl.lessons import load_lessons
from todoimpl.service.backend import _spawn
from todoimpl.todo_mcp.model import TodoError

DRAFT = '{"skill": "build-backend", "mistake": "m", "rule": "r", "evidence": "e"}'


def test_every_action_goes_to_the_scheduler_and_pokes_the_cache(rig: Rig) -> None:
    b = rig.backend
    b.start("t1")
    b.start("t1", auto_ship=True)
    b.spec_answers("t1", {"Q1": "a"})
    b.spec_ok("t1")
    b.send("t1", "hi")
    b.ship("t1")
    b.cancel("t1")
    b.credits("t1")
    assert rig.scheduler.calls == [
        ("start", "t1", None),
        ("start", "t1", True),
        ("spec_answers", "t1", {"Q1": "a"}),
        ("spec_ok", "t1"),
        ("send", "t1", "hi"),
        ("ship", "t1"),
        ("cancel", "t1"),
        ("credits", "t1"),
    ]


def test_todo_error_from_the_scheduler_is_a_visible_internal_error(rig: Rig) -> None:
    rig.scheduler.failure = TodoError("todo app down")
    with pytest.raises(BackendError, match="todo MCP: todo app down") as err:
        rig.backend.ship("t1")
    assert err.value.code == "upstream_unavailable"


def test_unknown_lesson_is_a_conflict(rig: Rig) -> None:
    with pytest.raises(BackendError, match="unknown lesson") as err:
        rig.backend.lesson_approve("t1", "nope")
    assert err.value.code == "conflict"


def run_inline(job: Callable[[], None]) -> None:
    job()


def test_send_at_the_gate_drafts_a_lesson(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "gate")
    rig.backend.spawn = run_inline
    rig.backend.drafter = lambda _prompt: DRAFT
    rig.backend.send(tid, "tests are fake, redo")
    assert [x.skill for x in load_lessons(run_dir(rig.root, tid))] == ["build-backend"]
    assert rig.scheduler.calls == [("send", tid, "tests are fake, redo")]
    assert "lesson-approve" in [a["id"] for a in rig.card(tid)["actions"]]


@pytest.mark.parametrize("stage", ["implement", None])
def test_send_outside_the_gate_drafts_nothing(rig: Rig, stage: str | None) -> None:
    spawned: list[Any] = []
    rig.backend.spawn = spawned.append
    if stage:
        rig.run("t1", stage)
    rig.backend.send("t1", "keep going")
    assert spawned == []


def test_a_failing_drafter_is_logged_and_the_send_still_happens(
    rig: Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.run("t1", "gate")
    rig.backend.spawn = run_inline

    def boom(_prompt: str) -> str:
        raise RuntimeError("claude not found")

    rig.backend.drafter = boom
    rig.backend.send("t1", "no")
    assert "lesson draft for t1 failed" in caplog.text
    assert rig.scheduler.calls == [("send", "t1", "no")]


def test_default_spawn_runs_the_job_on_a_thread() -> None:
    done = threading.Event()
    _spawn(done.set)
    assert done.wait(5)
