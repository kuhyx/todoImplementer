"""The free-model issue log: appending, reading hand-written lines, counting, finding unlogged fixes."""

from __future__ import annotations

from pathlib import Path

from todoimpl.umbrella import issues


def test_append_writes_one_json_line_with_the_agreed_fields(tmp_path: Path) -> None:
    issues.append(tmp_path, 10.0, "kuhyx/a", "start", "x" * 900, "retried", fixed=True, model="free-best")
    (row,) = issues.read(tmp_path)
    assert row == {
        "ts": 10.0,
        "child": "kuhyx/a",
        "phase": "start",
        "model": "free-best",
        "symptom": "x" * 500,
        "action": "retried",
        "fixed": True,
    }
    assert issues.raw(tmp_path).count("\n") == 1


def test_read_skips_lines_that_are_not_json_objects(tmp_path: Path) -> None:
    issues.path(tmp_path).write_text(
        '{"child": "kuhyx/a"}\nnot json\n[1]\n\n{"child": "kuhyx/a"}\n', encoding="utf-8"
    )
    assert len(issues.read(tmp_path)) == 2


def test_a_missing_log_is_empty(tmp_path: Path) -> None:
    assert issues.read(tmp_path) == []
    assert issues.raw(tmp_path) == ""
    assert issues.counts(tmp_path) == {}


def test_counts_per_child_repo(tmp_path: Path) -> None:
    for repo in ("kuhyx/a", "kuhyx/b", "kuhyx/a"):
        issues.append(tmp_path, 1.0, repo, "edit", "bad edit")
    issues.path(tmp_path).open("a", encoding="utf-8").write('{"phase": "x"}\n')
    assert issues.counts(tmp_path) == {"kuhyx/a": 2, "kuhyx/b": 1, "": 1}


def test_unlogged_finds_repos_without_a_line_since_the_round_began(tmp_path: Path) -> None:
    issues.append(tmp_path, 5.0, "kuhyx/a", "edit", "old")
    issues.append(tmp_path, 20.0, "kuhyx/b", "edit", "new")
    assert issues.unlogged(tmp_path, ["kuhyx/a", "kuhyx/b", "kuhyx/c"], since=10.0) == ["kuhyx/a", "kuhyx/c"]


def test_t2054_coaching_counts_the_prompt_lines_of_a_child_since_the_round_began(tmp_path: Path) -> None:
    issues.append(tmp_path, 5.0, "kuhyx/a", "prompt", "old")
    issues.append(tmp_path, 20.0, "kuhyx/a", "prompt", "misread")
    issues.append(tmp_path, 21.0, "kuhyx/a", "edit", "not coaching")
    issues.append(tmp_path, 22.0, "kuhyx/b", "prompt", "other child")
    assert issues.coaching(tmp_path, "kuhyx/a", since=10.0) == 1
