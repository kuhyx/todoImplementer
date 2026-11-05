"""Parsing of the server's plain-text tool results."""

from __future__ import annotations

import pytest
from todoimpl.todo_mcp.client import Task, TodoError
from todoimpl.todo_mcp.parse import added_id, parse_detail, parse_list, to_wire


def test_list_no_match_is_empty() -> None:
    assert parse_list("no tasks match") == []


def test_list_lines() -> None:
    text = "fda71ed1\ttodo\thigh\tkuhyx/utils\tutils todos\nabcdef12\tin_progress\tlow\t-\tx"
    assert parse_list(text) == [
        Task("fda71ed1", "utils todos", "", "kuhyx/utils", "todo", "high", None),
        Task("abcdef12", "x", "", None, "in progress", "low", None),
    ]


@pytest.mark.parametrize("text", ["a\tb\tc", "", "x\ttodo\thigh\tr\tt\textra"])
def test_list_malformed(text: str) -> None:
    with pytest.raises(TodoError, match="malformed"):
        parse_list(text)


def test_list_unknown_status() -> None:
    with pytest.raises(TodoError, match="status"):
        parse_list("fda71ed1\tweird\thigh\tr/x\tt")


DETAIL = (
    "id: fda71ed1-0000\npriority: high\nstatus: in_progress\ncreated: c\nupdated: u\n"
    "repo: kuhyx/utils\ndone_check: make test\nby: claude\n---\n# utils todos\n\n## a\nbody\n\n## b"
)


def test_detail_full() -> None:
    assert parse_detail(DETAIL) == Task(
        "fda71ed1", "utils todos", "## a\nbody\n\n## b", "kuhyx/utils", "in progress", "high", "make test"
    )


def test_detail_minimal_title_only() -> None:
    task = parse_detail("id: abcdef12xx\npriority: low\nstatus: todo\n---\nJust a title")
    assert task == Task("abcdef12", "Just a title", "", None, "todo", "low", None)


def test_detail_body_containing_separator() -> None:
    task = parse_detail("id: abcdef12xx\npriority: low\nstatus: todo\n---\nT\n\nline\n---\nmore")
    assert task.body == "line\n---\nmore"


def test_detail_blank_text() -> None:
    task = parse_detail("id: abcdef12xx\npriority: low\nstatus: todo\n---\n")
    assert (task.title, task.body) == ("", "")


@pytest.mark.parametrize(
    "text",
    ["no separator here", "priority: low\nstatus: todo\n---\nt", "id: abcdef12\npriority: low\n---\nt"],
)
def test_detail_malformed(text: str) -> None:
    with pytest.raises(TodoError, match="malformed"):
        parse_detail(text)


def test_detail_skips_lines_without_colon() -> None:
    task = parse_detail("id: abcdef12\njunk\npriority: low\nstatus: done\n---\nt")
    assert task.status == "done"


def test_added_id() -> None:
    assert added_id("added 0123456789abcdef\nline") == "01234567"
    assert added_id("appended to 76543210zz\nline") == "76543210"


def test_added_id_malformed() -> None:
    with pytest.raises(TodoError, match="malformed"):
        added_id("created something")


def test_to_wire() -> None:
    assert to_wire("in progress") == "in_progress"
    assert to_wire("in_progress") == "in_progress"
    assert to_wire("todo") == "todo"
