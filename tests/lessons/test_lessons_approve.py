from __future__ import annotations

import importlib
import json
from typing import Any

import pytest
from todoimpl.lessons import LessonError, approve, draft_lesson, load_lessons

approve_mod = importlib.import_module("todoimpl.lessons.approve")  # the package attribute is the function
GOOD = {
    "skill": "build-backend",
    "mistake": "m $(touch pwned)",
    "rule": "Never restart live.",
    "evidence": "e",
}


def drafted(env: Any) -> str:
    return draft_lesson(env.run_dir, "n", [], lambda _p: json.dumps(GOOD)).id


def test_approve_runs_skill_lesson_add_exactly_once(env: Any, lesson_validator: Any) -> None:
    lid = drafted(env)
    done = approve(env.run_dir, lid)
    assert done.state == "approved"
    lesson_validator.validate(done.to_dict())
    assert env.calls() == [
        [
            "add",
            "build-backend",
            "--mistake",
            "m $(touch pwned)",
            "--rule",
            "Never restart live.",
            "--evidence",
            "e",
        ]
    ]
    assert load_lessons(env.run_dir)[0].state == "approved"
    assert approve(env.run_dir, lid) == done  # idempotent: no second invocation
    assert len(env.calls()) == 1


def test_exit_2_means_recorded_and_consolidation_due(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_RC", "2")
    assert approve(env.run_dir, drafted(env)).state == "approved"


def test_exit_2_without_output_is_a_usage_error_not_a_record(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    lid = drafted(env)
    monkeypatch.setenv("FAKE_RC", "2")
    monkeypatch.setenv("FAKE_MSG", "")
    with pytest.raises(LessonError, match="exit 2"):
        approve(env.run_dir, lid)
    assert load_lessons(env.run_dir)[0].state == "drafted"


def test_failure_leaves_the_lesson_drafted_and_retryable(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    lid = drafted(env)
    monkeypatch.setenv("FAKE_RC", "1")
    monkeypatch.setenv("FAKE_MSG", "unknown skill: build-backend")
    with pytest.raises(LessonError, match="unknown skill"):
        approve(env.run_dir, lid)
    assert load_lessons(env.run_dir)[0].state == "drafted"
    monkeypatch.setenv("FAKE_RC", "0")
    assert approve(env.run_dir, lid).state == "approved"
    assert len(env.calls()) == 2


def test_unknown_lesson_id(env: Any) -> None:
    drafted(env)
    with pytest.raises(LessonError, match="unknown lesson"):
        approve(env.run_dir, "nope")
    assert env.calls() == []


def test_hanging_script_times_out(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    lid = drafted(env)
    (env.home / ".claude/scripts/skill_lesson.py").write_text("import time\ntime.sleep(5)\n")
    monkeypatch.setattr(approve_mod, "TIMEOUT_S", 0.3)
    with pytest.raises(LessonError, match="timed out"):
        approve(env.run_dir, lid)
    assert load_lessons(env.run_dir)[0].state == "drafted"


def test_missing_script_is_a_lesson_error(env: Any) -> None:
    lid = drafted(env)
    (env.home / ".claude/scripts/skill_lesson.py").unlink()
    with pytest.raises(LessonError, match="does not exist"):
        approve(env.run_dir, lid)
