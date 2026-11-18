"""POST /api/sessions/handoff over HTTP: the Ship gate, the new-task service, the card Start, the contract."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.sessions.commands import CommandResult
from todoimpl.tokens_api import paths

SID = "11111111-2222-4333-8444-555555555555"
ASKS = "99999999-8888-4777-8666-555555555555"
CWD = "/home/tester/src/demo"


class GitRunner:
    """Answers `git remote get-url origin` with a GitHub URL; anything else fails."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float = 10.0) -> CommandResult:
        self.calls.append(argv)
        if argv[:1] == ("git",) and argv[-3:] == ("remote", "get-url", "origin"):
            return CommandResult(argv, 0, "git@github.com:kuhyx/demo.git\n", "")
        return CommandResult(argv, 1, "", "unexpected")


class Tasks:
    """The new-task service the handoff drives: twin check, then create (returning the fake board's card)."""

    def __init__(self, card: str) -> None:
        self.card = card
        self.created: list[NewTask] = []
        self.conflict = False

    def check_twin(self, task: NewTask) -> None:
        if self.conflict:
            raise BackendError("conflict", f"{task.repo} already has an open part titled {task.title!r}")

    def create(self, task: NewTask) -> tuple[str, str]:
        self.created.append(task)
        return self.card[:8], self.card


def record(kind: str, ts: str, text: str) -> dict[str, Any]:
    base = {"cwd": CWD, "entrypoint": "cli", "isSidechain": False, "parentUuid": None, "userType": "external"}
    if kind == "user":
        return {**base, "type": "user", "timestamp": ts, "message": {"role": "user", "content": text}}
    content = [{"type": "text", "text": text}]
    return {
        **base,
        "type": "assistant",
        "timestamp": ts,
        "message": {"role": "assistant", "content": content},
    }


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """HOME=/home/tester under tmp: an untagged session (old) and one asking a question, plus a clone."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "home/tester/src"))
    (tmp_path / "home/tester/src/demo/.git").mkdir(parents=True)
    projects = tmp_path / "home/tester/.claude/projects/-home-tester-src-demo"
    projects.mkdir(parents=True)
    for sid, answer in ((SID, "half way there"), (ASKS, "Q: which one?")):
        lines = [
            record("user", "2026-11-10T08:00:00.000Z", "fix it"),
            record("assistant", "2026-11-10T08:00:02.000Z", answer),
        ]
        path = projects / f"{sid}.jsonl"
        path.write_text(
            "\n".join(json.dumps(r, separators=(",", ":")) for r in lines) + "\n", encoding="utf-8"
        )
        os.utime(path, (1_700_000_000, 1_700_000_000))
    from todoimpl.sessions import api, origin  # noqa: PLC0415 - after the env is set

    monkeypatch.setattr(api, "SCANNER", api.Scanner())
    monkeypatch.setattr(origin, "CACHE", origin.OriginCache())
    return tmp_path


@pytest.fixture
def git(live: Live) -> GitRunner:
    fake = GitRunner()
    live.server.router.sessions_runner = fake
    return fake


@pytest.fixture
def tasks(live: Live) -> Tasks:
    fake = Tasks(live.backend.task_id)
    live.backend.new_task_service = fake  # type: ignore[attr-defined]
    return fake


def post(live: Live, body: Any, **hdr: str) -> Any:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    return call(live.port, "POST", "/api/sessions/handoff", body, headers)


def listed(live: Live) -> dict[str, dict[str, Any]]:
    r = call(live.port, "GET", "/api/sessions")
    validate("sessions", r.json())
    return {row["id"]: row for row in r.json()["sessions"]}


def test_the_list_says_which_rows_can_move_and_why_not(live: Live, home: Path, git: GitRunner) -> None:
    rows = listed(live)
    assert (rows[SID]["movable"], rows[SID]["move_reason"]) == (True, None)
    assert rows[ASKS]["movable"] is False
    assert "asks you a question" in rows[ASKS]["move_reason"]


def test_handoff_creates_starts_and_drops_the_row(
    live: Live, home: Path, git: GitRunner, tasks: Tasks
) -> None:
    validate("sessions", {"ids": [SID], "repos": {SID: "kuhyx/demo"}}, "handoff_body")
    r = post(live, {"id": SID})
    assert r.status == 200, r.body
    validate("sessions", r.json(), "result")
    assert r.json()["ok"] is True, r.json()
    assert [t.repo for t in tasks.created] == ["kuhyx/demo"]
    assert live.backend.calls == [("start", live.backend.task_id, None)]
    assert listed(live)[SID]["done"] is True


def test_an_unmovable_row_is_refused_with_200(live: Live, home: Path, git: GitRunner, tasks: Tasks) -> None:
    r = post(live, {"ids": [SID, ASKS]})
    assert r.status == 200
    validate("sessions", r.json(), "result")
    assert r.json()["refused"] is True
    assert tasks.created == []


def test_a_twin_title_is_refused(live: Live, home: Path, git: GitRunner, tasks: Tasks) -> None:
    tasks.conflict = True
    assert post(live, {"id": SID}).json()["refused"] is True


def test_without_the_task_service_it_fails_cleanly(live: Live, home: Path, git: GitRunner) -> None:
    r = post(live, {"id": SID})
    assert (r.status, r.json()["ok"], r.json()["refused"]) == (200, False, False)


@pytest.mark.parametrize(
    "failure",
    [BackendError("upstream_unavailable", "board is busy"), RuntimeError("boom")],
    ids=["refused", "crash"],
)
def test_a_start_that_raises_still_moves_the_session(
    live: Live, home: Path, git: GitRunner, tasks: Tasks, failure: Exception
) -> None:
    live.backend.failure = failure
    r = post(live, {"id": SID})
    assert r.status == 200
    assert r.json()["ok"] is True
    assert "not started" in r.json()["stdout"]
    assert listed(live)[SID]["done"] is True


@pytest.mark.parametrize("bad", [{"Origin": "https://evil.example"}, {"X-Todoimpl-Token": "-"}])
def test_handoff_needs_the_origin_and_token(
    live: Live, home: Path, git: GitRunner, tasks: Tasks, bad: dict[str, str]
) -> None:
    r = post(live, {"id": SID}, **bad)
    assert r.status == 403
    assert tasks.created == []


@pytest.mark.parametrize(
    "body",
    [
        {"ids": [SID] * 6},
        {"id": SID, "repos": {SID: "no slash"}},
        {"id": SID, "repos": []},
        {"id": SID, "extra": 1},
    ],
)
def test_the_handoff_schema_rejects_what_the_server_refuses(body: dict[str, Any]) -> None:
    from jsonschema import ValidationError  # noqa: PLC0415

    with pytest.raises(ValidationError):
        validate("sessions", body, "handoff_body")
