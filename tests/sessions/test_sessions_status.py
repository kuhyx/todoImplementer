from __future__ import annotations

import pytest
from todoimpl.sessions import tags


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("All green.\nDONE: committed abc123, 12 passed", "done"),
        ("NEEDS ACTION: run `! sudo x`", "needs_action"),
        ("QUESTION: which branch?", "question"),
        ("RUNNING: CI on abc123, next check 5 min", "running"),
        ("just some prose, no tag", "untagged"),
        ("", "untagged"),
        # The tag is often followed by a NOTE line; every line is scanned.
        ("DONE: 3 tests pass\nNOTE: other dirty files in web/", "done"),
        ("  **DONE:** shipped", "done"),
        ("**NEEDS ACTION:** approve the push", "needs_action"),
        # A tag mid-sentence is prose, not a tag.
        ("I am not DONE: yet", "untagged"),
        # The one-letter tags CLAUDE.md asks for now (session 8bad89fe ended on
        # a "D:" line after prose and showed as untagged).
        ("Pushed.\n\nD: all done. 12 of 12 pass. Pushed:\n- a (1e1d52b)", "done"),
        ("R: CI on abc123, next check 5 min", "running"),
        ("Q: which branch?", "question"),
        ("A: run `! sudo x`", "needs_action"),
        ("C: /home/kuhy/.claude/handoff/x.md", "continuing"),
        ("**D:** shipped", "done"),
        ("D: done\nN: other dirty files", "done"),
        # A bare note is not a tag, and neither is a letter without the colon.
        ("N: note only", "untagged"),
        ("D-day is close", "untagged"),
    ],
)
def test_classifies_the_status_tag(text: str, expected: str) -> None:
    assert tags.classify(text) == expected


def test_continuing_matches_anywhere_and_case_insensitively() -> None:
    text = "Handed off.\nNEEDS ACTION: open it -- continuing In New Session abc"
    assert tags.classify(text) == "continuing"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("RUNNING: x\nQUESTION: y", "question"),
        ("QUESTION: y\nNEEDS ACTION: z", "needs_action"),
        ("NEEDS ACTION: z\nDONE: w", "done"),
        ("DONE: w\nCONTINUING in new session", "continuing"),
    ],
)
def test_precedence_when_several_tags_appear(text: str, expected: str) -> None:
    assert tags.classify(text) == expected


@pytest.mark.parametrize(
    "content",
    [
        "<command-name>/model</command-name>",
        "<local-command-stdout>Set model</local-command-stdout>",
        "<task-notification>agent finished</task-notification>",
        "<bash-input>ls</bash-input>",
        "<bash-stdout>x</bash-stdout>",
        [{"type": "tool_result", "tool_use_id": "t", "content": "ok"}],
    ],
)
def test_generated_user_content_is_not_a_prompt(content: object) -> None:
    record = {"type": "user", "message": {"role": "user", "content": content}}
    assert tags.prompt_text(record) is None


def test_meta_and_compact_summary_records_are_not_prompts() -> None:
    message = {"role": "user", "content": "hi"}
    assert tags.prompt_text({"message": message, "isMeta": True}) is None
    assert tags.prompt_text({"message": message, "isCompactSummary": True}) is None
    assert tags.prompt_text({"message": message, "isSidechain": True}) is None


def test_prompt_text_reads_strings_and_text_blocks() -> None:
    assert tags.prompt_text({"message": {"content": "  hi  "}}) == "hi"
    blocks = [
        {"type": "text", "text": "<system-reminder>ctx</system-reminder>"},
        {"type": "text", "text": "real ask"},
    ]
    assert tags.prompt_text({"message": {"content": blocks}}) == "real ask"


def test_assistant_text_joins_only_text_blocks() -> None:
    blocks = [
        {"type": "thinking", "thinking": "secret"},
        {"type": "text", "text": "a"},
        {"type": "tool_use", "name": "Bash"},
        {"type": "text", "text": "b"},
    ]
    assert tags.assistant_text({"message": {"content": blocks}}) == "a\nb"
    assert tags.assistant_text({"message": {"content": [blocks[0]]}}) is None
    assert tags.assistant_text({"message": {"content": "x"}}) is None


def test_a_record_without_a_message_is_not_a_prompt() -> None:
    assert tags.prompt_text({"type": "user"}) is None
    image = [{"type": "image", "source": {}}]
    assert tags.prompt_text({"message": {"content": image}}) == "[image]"
