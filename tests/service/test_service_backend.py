"""ServiceBackend reads: board, task, usage, errors, lessons, live set, limit."""

import time
from collections.abc import Callable
from pathlib import Path

import pytest
from contract_lib import validate
from servicefakes import Rig, write_stream
from todoimpl.board.state import run_dir
from todoimpl.http.backend import BackendError
from todoimpl.lessons.store import Lesson, save_lessons
from todoimpl.service import ServiceBackend, TaskCache
from todoimpl.service.cards import CardTask, card_tasks
from todoimpl.todo_mcp.model import Task


def test_board_before_any_successful_fetch_is_an_upstream_error(rig: Rig) -> None:
    with pytest.raises(BackendError, match="todo MCP: notes not loaded") as err:
        rig.backend.board()
    assert err.value.code == "upstream_unavailable"


def test_board_has_one_valid_card_per_section(rig: Rig) -> None:
    note = rig.note(body="## a\nx\n## b\ny", priority="high")
    rig.note(title="solo", repo="kuhyx/other")
    board = rig.backend.board()
    validate("board", board)
    assert board["build"] == "b1"
    assert board["repos"] == ["kuhyx/demo", "kuhyx/other"]
    ids = [c["id"] for c in board["tasks"]]
    assert len(ids) == 3
    assert len(set(ids)) == 3
    assert note in ids
    assert board["slots"] == {"used": 0}


def test_mcp_failure_keeps_the_last_cards_and_adds_the_banner(rig: Rig) -> None:
    tid = rig.note()
    assert "error" not in rig.backend.board()
    rig.fake.fail_method("tools/call", 500)
    rig.backend.cache.refresh()
    board = rig.backend.board()
    validate("board", board)
    assert [c["id"] for c in board["tasks"]] == [tid]
    assert board["error"]["code"] == "upstream_unavailable"
    assert board["error"]["message"].startswith("todo MCP: ")
    assert rig.backend.task(tid) is not None
    rig.fake.fail_method("tools/call", None)
    rig.backend.cache.refresh()
    assert "error" not in rig.backend.board()


def test_running_set_and_run_state_decide_the_status(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "implement")
    rig.scheduler.live = {tid}
    card = rig.card(tid)
    assert (card["status"], card["column"]) == ("working", "running")
    assert rig.backend.board()["slots"]["used"] == 1


def test_active_limit_shows_in_the_board(rig: Rig) -> None:
    rig.note()
    rig.root.mkdir(parents=True, exist_ok=True)
    (rig.root / "limit-until").write_text(str(time.time() + 3600), encoding="utf-8")
    limit = rig.backend.board()["limit"]
    assert limit["active"] is True
    assert limit["until"] > time.time()
    assert limit["credits"]["state"] == "unavailable"


def test_task_detail_validates_and_unknown_is_none(rig: Rig) -> None:
    tid = rig.note(body="## a\nx")
    detail = rig.backend.task(tid)
    assert detail is not None
    validate("task", detail)
    assert detail["card"]["id"] == tid
    assert rig.backend.task("zzzzzzzz") is None


def test_task_detail_reads_diff_questions_and_stage(rig: Rig, tmp_path: Path) -> None:
    tid = rig.note()
    rig.run(tid, "gate", worktree=str(tmp_path / "no-such-worktree"), base_sha="abc")
    detail = rig.backend.task(tid)
    assert detail is not None
    validate("task", detail)
    assert detail["diff"] is None
    assert detail["card"]["stage"] == "gate"


def test_drafted_lesson_and_streams_reach_the_card_and_drawer(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "gate")
    directory = run_dir(rig.root, tid)
    save_lessons(directory, [Lesson("l1", "build-backend", "m", "r", "e")])
    write_stream(directory, ["build-backend", "unified-design-system"])
    detail = rig.backend.task(tid)
    assert detail is not None
    validate("task", detail)
    assert detail["lesson"]["id"] == "l1"
    assert detail["skills_loaded"] == ["build-backend", "unified-design-system"]
    assert "lesson-approve" in [a["id"] for a in rig.card(tid)["actions"]]


def test_corrupt_lessons_file_shows_as_a_run_error_not_a_dead_board(rig: Rig) -> None:
    tid = rig.note()
    rig.run(tid, "gate")
    (run_dir(rig.root, tid) / "lessons.json").write_text("{nope", encoding="utf-8")
    detail = rig.backend.task(tid)
    assert detail is not None
    assert "corrupt" in detail["error"]
    assert rig.backend.board()["tasks"]


def test_usage_validates_and_names_tasks(rig: Rig) -> None:
    tid = rig.note(title="Named note")
    write_stream(run_dir(rig.root, tid), [])
    usage = rig.backend.usage()
    validate("usage", usage)
    assert usage["cost"]["per_task"][0]["title"] == "Named note"


def test_usage_works_while_the_todo_app_is_down(rig: Rig) -> None:
    assert rig.backend.usage()["cost"]["per_task"] == []


def test_subscribe_comes_from_the_scheduler(rig: Rig) -> None:
    rig.scheduler.events = [{"type": "cost", "cost_usd": 1.0}]
    assert list(rig.backend.subscribe("abcdef12")) == [{"type": "cost", "cost_usd": 1.0}]


def test_board_and_task_answer_fast_with_400_cards(rig: Rig) -> None:
    fakes = [
        c
        for i in range(400)
        for c in card_tasks(
            Task(f"{i:08x}", f"note {i}", "## a\nx\n## b\ny", "kuhyx/demo", "todo", "low", None)
        )
    ]
    backend = ServiceBackend(TaskCache(lambda: fakes), rig.scheduler, rig.root, "b1")
    backend.cache.refresh()
    assert len(fakes) == 800
    calls: list[Callable[[], object]] = [backend.board, lambda: backend.task(fakes[5].id), backend.usage]
    for call in calls:
        started = time.perf_counter()
        call()
        assert time.perf_counter() - started < 1.0


def test_card_type_is_exported() -> None:
    assert CardTask.__name__ == "CardTask"


def test_shot_serves_only_plain_pngs_inside_the_run_dir(rig: Rig) -> None:
    tid = rig.note()
    shots = run_dir(rig.root, tid) / "shots"
    shots.mkdir(parents=True)
    (shots / "home.png").write_bytes(b"png")
    (shots / "dir.png").mkdir()
    (shots / "notes.txt").write_text("x", encoding="utf-8")
    (run_dir(rig.root, tid) / "state.json").write_text("{}", encoding="utf-8")
    assert rig.backend.shot(tid, "home.png") == b"png"
    for name in ("missing.png", "dir.png", "notes.txt", "../state.json", "../shots/home.png", ""):
        assert rig.backend.shot(tid, name) is None


def test_unreadable_shot_is_none(rig: Rig) -> None:
    tid = rig.note()
    shots = run_dir(rig.root, tid) / "shots"
    shots.mkdir(parents=True)
    locked = shots / "locked.png"
    locked.write_bytes(b"x")
    locked.chmod(0)
    try:
        assert rig.backend.shot(tid, "locked.png") is None
    finally:
        locked.chmod(0o600)


def test_t1400_nested_shots_are_served_and_symlink_escapes_refused(rig: Rig, tmp_path: Path) -> None:
    tid = rig.note()
    shots = run_dir(rig.root, tid) / "shots"
    (shots / "live2").mkdir(parents=True)
    (shots / "live2" / "v1-1366x768.png").write_bytes(b"deep")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "secret.png").write_bytes(b"secret")
    (shots / "link").symlink_to(outside)
    (shots / "evil.png").symlink_to(outside / "secret.png")
    assert rig.backend.shot(tid, "live2/v1-1366x768.png") == b"deep"
    deep = "live2/v1-1366x768.png"
    bad = ("link/secret.png", "evil.png", f"live2/../{deep}", f"./{deep}", "live2//v1.png", f"/{deep}")
    for name in bad:
        assert rig.backend.shot(tid, name) is None
