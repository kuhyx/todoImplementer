from __future__ import annotations

import json
from typing import Any

import pytest
from todoimpl.lessons import LessonError, draft, draft_lesson, latest_lesson, load_lessons

GOOD = {
    "skill": "build-backend",
    "mistake": "restarted the live server in a test",
    "rule": "Never restart the live server from tests.",
    "evidence": "gate rejection: server was down",
}


class Drafter:
    """Injectable stand-in for the haiku call; records the prompts it saw."""

    def __init__(self, payload: Any) -> None:
        self.text = payload if isinstance(payload, str) else json.dumps(payload)
        self.seen: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.seen.append(prompt)
        return self.text


drafter = Drafter


def test_draft_is_stored_and_contract_valid(env: Any, lesson_validator: Any) -> None:
    call = drafter(GOOD)
    lesson = draft_lesson(env.run_dir, "You restarted prod.", ["grilling"], call)
    lesson_validator.validate(json.loads(json.dumps(lesson.to_dict())))
    assert (lesson.skill, lesson.state, lesson.rule) == ("build-backend", "drafted", GOOD["rule"])
    assert load_lessons(env.run_dir) == [lesson]
    assert latest_lesson(env.run_dir) == lesson
    stored = json.loads((env.run_dir / "lessons.json").read_text())
    assert stored["lessons"][0]["id"] == lesson.id
    prompt = call.seen[0]
    assert prompt.startswith("override\n")
    assert "You restarted prod." in prompt
    assert "grilling" in prompt
    assert "build-web-ui" in prompt
    assert "build-empty" not in prompt


def test_skill_may_be_a_loaded_non_build_skill(env: Any) -> None:
    lesson = draft_lesson(env.run_dir, "n", ["textgate"], drafter({**GOOD, "skill": "textgate"}))
    assert lesson.skill == "textgate"


def test_json_in_a_code_fence_with_chatter_is_accepted(env: Any) -> None:
    text = "Here you go:\n```json\n" + json.dumps(GOOD) + "\n```\nDone."
    assert draft_lesson(env.run_dir, "n", [], drafter(text)).rule == GOOD["rule"]


def test_same_draft_twice_is_one_lesson_and_keeps_state(env: Any) -> None:
    first = draft_lesson(env.run_dir, "n", [], drafter(GOOD))
    again = draft_lesson(env.run_dir, "n", [], drafter(GOOD))
    assert again == first
    assert len(load_lessons(env.run_dir)) == 1
    other = draft_lesson(env.run_dir, "n", [], drafter({**GOOD, "rule": "Another rule."}))
    assert latest_lesson(env.run_dir) == other
    assert len(load_lessons(env.run_dir)) == 2


@pytest.mark.parametrize(
    "payload",
    [
        "no json here",
        "{broken",
        "{ not json }",
        "[1]",
        "{}",
        {**GOOD, "skill": "not-a-skill"},
        {**GOOD, "rule": ""},
        {**GOOD, "mistake": 3},
        {k: v for k, v in GOOD.items() if k != "evidence"},
    ],
)
def test_unusable_model_output_fails_closed(env: Any, payload: Any) -> None:
    with pytest.raises(LessonError):
        draft_lesson(env.run_dir, "n", ["grilling"], drafter(payload))
    assert not (env.run_dir / "lessons.json").exists()
    assert latest_lesson(env.run_dir) is None


def test_corrupt_store_is_an_error_not_an_empty_list(env: Any) -> None:
    for bad in ("not json", '{"lessons": [{"id": "x"}]}', '{"lessons": 3}'):
        (env.run_dir / "lessons.json").write_text(bad)
        with pytest.raises(LessonError):
            load_lessons(env.run_dir)


def test_default_drafter_runs_haiku_one_shot_without_auto_continue(env: Any, claude_says: Any) -> None:
    claude_says(json.dumps(GOOD))
    lesson = draft_lesson(env.run_dir, "You restarted prod.", ["grilling"])
    (call,) = env.calls()
    assert call["argv"] == ["-p", "--model", "haiku", "--output-format", "json", "--strict-mcp-config"]
    assert call["auto"] == "0"
    assert call["stdin"].startswith("override\n")
    assert "You restarted prod." in call["stdin"]
    assert lesson.skill == "build-backend"


@pytest.mark.parametrize("stdout", ["not json", "[1]", '{"result": 5}', '{"is_error": true, "result": "x"}'])
def test_default_drafter_rejects_a_bad_envelope(
    env: Any, monkeypatch: pytest.MonkeyPatch, stdout: str
) -> None:
    monkeypatch.setenv("FAKE_STDOUT", stdout)
    with pytest.raises(LessonError):
        draft_lesson(env.run_dir, "n", [])


def test_default_drafter_reports_nonzero_exit(env: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STDOUT", "boom")
    monkeypatch.setenv("FAKE_RC", "3")
    with pytest.raises(LessonError, match="exit 3"):
        draft_lesson(env.run_dir, "n", [])


def test_default_drafter_reports_timeout_and_missing_binary(
    env: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FAKE_STDOUT", "{}")
    monkeypatch.setenv("FAKE_SLEEP", "5")
    monkeypatch.setattr(draft, "CLAUDE_TIMEOUT_S", 0.3)
    with pytest.raises(LessonError, match="timed out"):
        draft_lesson(env.run_dir, "n", [])
    empty = env.home / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))
    with pytest.raises(LessonError, match="cannot run claude"):
        draft_lesson(env.run_dir, "n", [])
