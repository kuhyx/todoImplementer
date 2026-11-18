"""Which manual sessions may move to the board (server-computed `movable` / `move_reason`) and cwd -> repo."""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING

import pytest
import sessfix as fx
from contract_lib import validate
from sessrunner import FakeRunner, ok
from todoimpl.sessions import api, mark, movable, origin

if TYPE_CHECKING:
    from pathlib import Path

# 2026-10-22T08:00:02Z, the default answer time of sessfix, plus offsets.
ANSWERED = 1792656002.0
HOUR = 3600


def git_argv(sysroot: Path, cwd: str = fx.CWD) -> tuple[str, ...]:
    return ("git", "-C", str(sysroot / cwd.lstrip("/")), "remote", "get-url", "origin")


@pytest.fixture
def src(sysroot: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make the source root with a clone of kuhyx/demo, which is also the session cwd."""
    root = sysroot / "home/tester/src"
    (root / "demo/.git").mkdir(parents=True)
    monkeypatch.setenv("TODOIMPL_SRC", str(root))
    monkeypatch.setattr(movable, "now", lambda: ANSWERED + 2 * HOUR)
    return root


def runner_for(sysroot: Path, url: str = "git@github.com:kuhyx/demo.git") -> FakeRunner:
    argv = git_argv(sysroot)
    return FakeRunner({argv: ok(argv, url + "\n")})


def rows(runner: FakeRunner) -> dict[str, dict[str, object]]:
    body = api.listing(runner)
    validate("sessions", body)
    return {row["id"]: row for row in body["sessions"]}


@pytest.mark.parametrize(
    ("url", "repo"),
    [
        ("https://github.com/kuhyx/demo.git", "kuhyx/demo"),
        ("https://github.com/kuhyx/demo", "kuhyx/demo"),
        ("https://x-access-token:abc@github.com/kuhyx/demo.git", "kuhyx/demo"),
        ("git@github.com:kuhyx/demo.git", "kuhyx/demo"),
        ("ssh://git@github.com/kuhyx/my.repo/", "kuhyx/my.repo"),
        ("https://codeberg.org/kuhyx/demo.git", None),
        ("git@github.com:kuhyx/demo/extra.git", None),
        ("/srv/git/demo.git", None),
        ("", None),
    ],
)
def test_origin_urls_map_to_owner_name(url: str, repo: str | None) -> None:
    assert origin.github_repo(url) == repo


@pytest.mark.parametrize(
    ("answer", "hours", "manual", "expected"),
    [
        ("still thinking", 0.1, False, None),
        ("R: tests run", 1.0, False, None),
        ("R: tests run", 0.5, False, "still running"),
        ("A: approve the push", 5, False, "waits for your action"),
        ("Q: which one?", 5, False, "asks you a question"),
        ("D: shipped", 5, False, "already done"),
        ("C: ~/handoff.md", 5, False, "already done"),
        ("still thinking", 5, True, "already done"),
    ],
)
def test_only_untagged_and_stale_running_sessions_are_movable(
    sysroot: Path,
    src: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    answer: str,
    hours: float,
    manual: bool,
    expected: str | None,
) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session(answer))
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(movable, "now", lambda: ANSWERED + hours * HOUR)
    if manual:
        mark.write_marks(api.marks_path(), {fx.SID: {"mark": "done", "at": 1}})
    runner = runner_for(sysroot)
    row = rows(runner)[fx.SID]
    assert row["movable"] is (expected is None)
    if expected is None:
        assert row["move_reason"] is None
        assert runner.calls == [git_argv(sysroot)]
    else:
        assert expected in str(row["move_reason"])
        assert runner.calls == []  # a blocked status never costs a git call


def test_a_cwd_without_a_github_origin_says_so(sysroot: Path, src: Path) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session("no tag"))
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    row = rows(FakeRunner({}))[fx.SID]
    assert row["movable"] is False
    assert "no GitHub origin" in str(row["move_reason"])
    assert "repos" in str(row["move_reason"])


def test_a_vanished_cwd_is_not_movable_and_runs_no_git(sysroot: Path, src: Path) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session("no tag"))
    shutil.rmtree(src / "demo")
    runner = runner_for(sysroot)
    row = rows(runner)[fx.SID]
    assert (row["movable"], runner.calls) == (False, [])
    assert "no longer exists" in str(row["move_reason"])


def test_an_origin_without_a_local_clone_is_not_movable(sysroot: Path, src: Path) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session("no tag"))
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    row = rows(runner_for(sysroot, "https://github.com/kuhyx/elsewhere"))[fx.SID]
    assert row["movable"] is False
    assert "no clone of kuhyx/elsewhere" in str(row["move_reason"])


def test_the_origin_is_read_once_per_cwd_while_fresh(
    sysroot: Path, src: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for sid in (fx.SID, fx.OTHER_SID):
        fx.write(fx.projects_dir(sysroot), fx.session("no tag"), sid=sid)
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    runner = runner_for(sysroot)
    clock = [100.0]
    monkeypatch.setattr(origin, "now", lambda: clock[0])
    assert all(row["movable"] for row in rows(runner).values())
    rows(runner)
    assert len(runner.calls) == 1
    clock[0] += origin.TTL_SECONDS + 1
    rows(runner)
    assert len(runner.calls) == 2


def test_a_running_session_without_any_time_uses_the_file_age(
    sysroot: Path, src: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = fx.session("R: going")
    for record in records:
        record.pop("timestamp", None)
    path = fx.write(fx.projects_dir(sysroot), records)
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(movable, "now", lambda: path.stat().st_mtime + 10)
    assert "still running" in str(rows(runner_for(sysroot))[fx.SID]["move_reason"])
    monkeypatch.setattr(movable, "now", lambda: path.stat().st_mtime + 2 * HOUR)
    assert rows(runner_for(sysroot))[fx.SID]["movable"] is True


def test_a_garbled_time_falls_back_to_the_file_age(
    sysroot: Path, src: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    records = fx.session("R: going")
    for record in records:
        if "timestamp" in record:
            record["timestamp"] = "yesterday-ish"
    path = fx.write(fx.projects_dir(sysroot), records)
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(movable, "now", lambda: path.stat().st_mtime + 2 * HOUR)
    assert rows(runner_for(sysroot))[fx.SID]["movable"] is True


def test_an_override_repo_must_be_well_formed_and_cloned(sysroot: Path, src: Path) -> None:
    fx.write(fx.projects_dir(sysroot), fx.session("no tag"))
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True, exist_ok=True)
    session = api.find(fx.SID)
    assert session is not None
    runner = FakeRunner({})
    assert movable.verdict(runner, session, None, "kuhyx/demo") == ("kuhyx/demo", None)
    assert movable.verdict(runner, session, None, "not a repo")[1] == "repo must look like owner/name"
    assert "no clone of kuhyx/nope" in str(movable.verdict(runner, session, None, "kuhyx/nope")[1])
    assert runner.calls == []  # an override never asks git


def test_the_shared_fixture_carries_the_new_fields() -> None:
    from pathlib import Path  # noqa: PLC0415

    fixture = json.loads((Path(__file__).parent.parent / "fixtures/sessions.json").read_text("utf-8"))
    assert {"movable", "move_reason"} <= set(fixture["sessions"][0])
