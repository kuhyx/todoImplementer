from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl.lessons import run_skills, skills_loaded, streams

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def skill_use(name: object = "grilling", tool: str = "Skill") -> dict[str, Any]:
    return {
        "type": "assistant",
        "message": {
            "content": [
                {"type": "text", "text": "hi"},
                {"type": "tool_use", "id": "t1", "name": tool, "input": {"skill": name}},
            ]
        },
    }


def write(path: Path, events: list[Any]) -> Path:
    path.write_text("\n".join(e if isinstance(e, str) else json.dumps(e) for e in events) + "\n")
    return path


def test_ordered_unique_skill_names(tmp_path: Path) -> None:
    stream = write(
        tmp_path / "a.stream.jsonl",
        [
            skill_use("build-backend"),
            skill_use("grilling"),
            skill_use("build-backend"),
            skill_use("textgate"),
        ],
    )
    assert skills_loaded(stream) == ["build-backend", "grilling", "textgate"]


def test_ignores_everything_that_is_not_a_skill_tool_use(tmp_path: Path) -> None:
    stream = write(
        tmp_path / "a.stream.jsonl",
        [
            skill_use("x", tool="Bash"),
            skill_use(7),
            skill_use(""),
            "garbage",
            "[]",
            {"type": "assistant", "message": "text"},
            {"type": "assistant", "message": {"content": "x"}},
            {
                "type": "assistant",
                "message": {"content": ["x", {"type": "tool_use", "name": "Skill", "input": 3}]},
            },
            {"type": "user"},
            skill_use("ok"),
        ],
    )
    assert skills_loaded(stream) == ["ok"]


def test_missing_stream_means_no_skills(tmp_path: Path) -> None:
    assert skills_loaded(tmp_path / "none.stream.jsonl") == []


def test_run_skills_merges_all_streams_of_a_run(tmp_path: Path) -> None:
    write(tmp_path / "1-plan.stream.jsonl", [skill_use("a"), skill_use("b")])
    write(tmp_path / "2-impl.stream.jsonl", [skill_use("b"), skill_use("c")])
    assert run_skills(tmp_path) == ["a", "b", "c"]


def test_t1908_an_unchanged_stream_is_parsed_once(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every /api/board re-parsed every stream of every run (137k events, 4 s); now cached."""
    parsed: list[Path] = []
    real = streams.iter_events

    def counting(path: Path) -> Any:
        parsed.append(path)
        return real(path)

    monkeypatch.setattr(streams, "iter_events", counting)
    stream = write(tmp_path / "a.stream.jsonl", [skill_use("grilling")])
    assert skills_loaded(stream) == skills_loaded(stream) == ["grilling"]
    assert len(parsed) == 1
    write(stream, [skill_use("grilling"), skill_use("textgate")])  # the file grew: read it again
    assert skills_loaded(stream) == ["grilling", "textgate"]
    assert len(parsed) == 2


def test_a_missing_stream_has_no_skills_and_the_cache_is_bounded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert skills_loaded(tmp_path / "gone.stream.jsonl") == []
    monkeypatch.setattr(streams, "CACHE_MAX", 1)
    one = write(tmp_path / "1.stream.jsonl", [skill_use("grilling")])
    two = write(tmp_path / "2.stream.jsonl", [skill_use("textgate")])
    assert skills_loaded(one) == ["grilling"]
    assert skills_loaded(two) == ["textgate"]
    assert list(streams._CACHE) == [two]
