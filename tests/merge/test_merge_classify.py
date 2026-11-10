"""The Haiku classifier: prompt, output validation and the one-shot `claude -p` call."""

import json
from pathlib import Path

import pytest
from test_merge_text import card
from todoimpl.merge import classify

IDS = {"aaaaaaaa-0", "bbbbbbbb-0", "cccccccc-0", "dddddddd-0"}


def group(ids: object, title: object = "T", reason: object = "same kind") -> dict[str, object]:
    return {"ids": ids, "title": title, "reason": reason}


def parse(groups: object, ids: set[str] = IDS) -> list[classify.Group]:
    return classify.parse_groups(json.dumps({"groups": groups}), ids)


def test_prompt_lists_id_repo_title_and_the_first_300_chars() -> None:
    c = card("aaaaaaaa", 0, "Make x text-free", "y" * 400, repo="kuhyx/x")
    prompt = classify.build_prompt([c])
    assert "aaaaaaaa-0 | kuhyx/x | Make x text-free | " + "y" * 300 in prompt
    assert "y" * 301 not in prompt
    assert prompt.startswith("override\n")


def test_prompt_flattens_newlines_of_the_body() -> None:
    assert "a b" in classify.build_prompt([card("aaaaaaaa", 0, "t", "a\nb")])


def test_valid_groups_pass_and_ids_are_deduplicated_in_order() -> None:
    got = parse([group(["aaaaaaaa-0", "bbbbbbbb-0", "aaaaaaaa-0"], " Title ", " why\nsecond line ")])
    assert got == [classify.Group(("aaaaaaaa-0", "bbbbbbbb-0"), "Title", "why")]


@pytest.mark.parametrize(
    "bad",
    [
        group(["aaaaaaaa-0"]),  # one member
        group(["aaaaaaaa-0", "aaaaaaaa-0"]),  # one distinct member
        group(["aaaaaaaa-0", "zzzzzzzz-0"]),  # unknown id
        group(["aaaaaaaa-0", 5]),  # not text
        group("aaaaaaaa-0"),  # ids not a list
        group(["aaaaaaaa-0", "bbbbbbbb-0"], title=""),
        group(["aaaaaaaa-0", "bbbbbbbb-0"], reason=" "),
        group(["aaaaaaaa-0", "bbbbbbbb-0"], title=3),
        "not an object",
    ],
)
def test_invalid_groups_are_dropped(bad: object) -> None:
    assert parse([bad]) == []


def test_a_note_in_two_groups_keeps_only_the_first_group() -> None:
    got = parse(
        [
            group(["aaaaaaaa-0", "bbbbbbbb-0"]),
            group(["bbbbbbbb-0", "cccccccc-0"]),
            group(["cccccccc-0", "dddddddd-0"]),
        ]
    )
    assert [g.ids for g in got] == [("aaaaaaaa-0", "bbbbbbbb-0"), ("cccccccc-0", "dddddddd-0")]


@pytest.mark.parametrize(
    "text", ["", "no json", "{broken", "{nope}", '{"groups": 3}', '["a"]', '{"other": []}']
)
def test_garbage_output_is_an_error(text: str) -> None:
    with pytest.raises(classify.ClassifyError):
        classify.parse_groups(text, IDS)


def test_json_inside_chatter_is_accepted() -> None:
    body = json.dumps({"groups": [group(["aaaaaaaa-0", "bbbbbbbb-0"])]})
    assert len(classify.parse_groups(f"Sure:\n```json\n{body}\n```", IDS)) == 1


def envelope(text: str, **extra: object) -> str:
    return json.dumps({"type": "result", "is_error": False, "result": text, **extra})


def test_claude_call_is_haiku_read_only_one_shot(shim: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FAKE_STDOUT", envelope("hello"))
    assert classify.claude_classifier("the prompt") == "hello"
    call = json.loads(shim.read_text().splitlines()[0])
    argv = call["argv"]
    assert argv[:7] == [
        "-p",
        "--model",
        "haiku",
        "--output-format",
        "json",
        "--strict-mcp-config",
        "--disallowedTools",
    ]
    assert "Edit" in argv[7]
    assert "Bash(git push:*)" in argv[7]
    assert call["stdin"] == "the prompt"
    assert call["auto"] == "0"


@pytest.mark.parametrize(
    ("stdout", "rc", "why"),
    [
        ("oops", "1", "exit 1"),
        ("not json", "0", "non-JSON"),
        (envelope("x", is_error=True), "0", "no text"),
        ('{"result": 5}', "0", "no text"),
    ],
)
def test_claude_failures_are_classify_errors(
    shim: Path, monkeypatch: pytest.MonkeyPatch, stdout: str, rc: str, why: str
) -> None:
    monkeypatch.setenv("FAKE_STDOUT", stdout)
    monkeypatch.setenv("FAKE_RC", rc)
    with pytest.raises(classify.ClassifyError, match=why):
        classify.claude_classifier("p")


def test_claude_timeout_and_missing_binary(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    sleeper = tmp_path / "claude"
    sleeper.write_text("#!/bin/sh\nsleep 5\n")
    sleeper.chmod(0o755)
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(sleeper))
    monkeypatch.setattr(classify, "TIMEOUT_S", 0.2)
    with pytest.raises(classify.ClassifyError, match="timed out"):
        classify.claude_classifier("p")
    monkeypatch.setenv("TODOIMPL_CLAUDE", str(tmp_path / "missing"))
    with pytest.raises(classify.ClassifyError, match="cannot run claude"):
        classify.claude_classifier("p")
