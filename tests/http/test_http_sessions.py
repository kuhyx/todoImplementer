"""GET /api/sessions and POST /api/sessions/<resume|mark|delete>: contract, gate, hermetic ~/.claude."""

import json
import os
from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.sessions.commands import CommandResult
from todoimpl.tokens_api import paths

SID = "11111111-2222-4333-8444-555555555555"
OTHER = "99999999-8888-4777-8666-555555555555"
HEADLESS = "aaaaaaaa-2222-4333-8444-555555555555"
CWD = "/home/tester/src/demo"
SHOW_ENV = ("systemctl", "--user", "show-environment")
DENIED = [
    {"Origin": "https://evil.example"},
    {"Origin": "-"},
    {"X-Todoimpl-Token": "-"},
    {"X-Todoimpl-Token": "nope"},
]


class Runner:
    """Records every command; answers each with a success."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float = 10.0) -> CommandResult:
        self.calls.append(argv)
        stdout = "DISPLAY=:7\n" if argv == SHOW_ENV else "Running as unit: x.service"
        return CommandResult(argv=argv, returncode=0, stdout=stdout, stderr="")


def transcript(answer: str, entrypoint: str = "cli") -> str:
    """Build a two-record transcript: one typed prompt, one tagged answer."""
    base = {
        "cwd": CWD,
        "entrypoint": entrypoint,
        "isSidechain": False,
        "parentUuid": None,
        "userType": "external",
    }
    user = {
        **base,
        "type": "user",
        "timestamp": "2026-11-10T08:00:00.000Z",
        "message": {"role": "user", "content": "fix it"},
    }
    block = {"type": "text", "text": answer}
    reply = {
        **base,
        "type": "assistant",
        "timestamp": "2026-11-10T08:00:02.000Z",
        "message": {"role": "assistant", "content": [block]},
    }
    return "\n".join(json.dumps(r, separators=(",", ":")) for r in (user, reply)) + "\n"


@pytest.fixture
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Build a temp root with HOME=/home/tester, three transcripts (one headless) and the cwd of the first."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("HOME", "/home/tester")
    projects = tmp_path / "home/tester/.claude/projects/-home-tester-src-demo"
    projects.mkdir(parents=True)
    (tmp_path / CWD.lstrip("/")).mkdir(parents=True)
    for sid, answer, entry in (
        (SID, "A: approve the push", "cli"),
        (OTHER, "D: done", "cli"),
        (HEADLESS, "D: x", "sdk-cli"),
    ):
        path = projects / f"{sid}.jsonl"
        path.write_text(transcript(answer, entry), encoding="utf-8")
        os.utime(path, (1_700_000_000, 1_700_000_000))
    from todoimpl.sessions import api  # noqa: PLC0415 - after the env is set

    monkeypatch.setattr(api, "SCANNER", api.Scanner())
    return tmp_path


@pytest.fixture
def runner(live: Live) -> Runner:
    fake = Runner()
    live.server.router.sessions_runner = fake
    return fake


def post(live: Live, name: str, body: Any = None, **hdr: str) -> Any:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    return call(live.port, "POST", f"/api/sessions/{name}", body, headers)


def marks(home: Path) -> Path:
    return home / "home/tester/.claude/session-status.json"


def test_get_lists_manual_sessions_in_the_contract_shape(live: Live, home: Path) -> None:
    r = call(live.port, "GET", "/api/sessions")
    assert r.status == 200
    validate("sessions", r.json())
    rows = r.json()["sessions"]
    assert [(row["id"], row["status"], row["group"]) for row in rows] == [
        (SID, "needs_action", 0),
        (OTHER, "done", 4),
    ]
    assert HEADLESS not in {row["id"] for row in rows}
    assert r.headers["cache-control"] == "no-store"


def test_get_needs_no_token(live: Live, home: Path) -> None:
    assert call(live.port, "GET", "/api/sessions", headers={"Origin": "https://evil.example"}).status == 200


def test_get_with_no_claude_dir_is_an_empty_list(
    live: Live, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    r = call(live.port, "GET", "/api/sessions")
    assert r.json()["sessions"] == []


def test_a_sub_path_of_get_is_not_found(live: Live, home: Path) -> None:
    assert call(live.port, "GET", "/api/sessions/resume").status == 404


def test_mark_writes_the_shared_marks_file_and_the_list_follows(
    live: Live, home: Path, runner: Runner
) -> None:
    body = {"ids": [SID], "mark": "done"}
    validate("sessions", body, "mark_body")
    r = post(live, "mark", body)
    assert r.status == 200
    validate("sessions", r.json(), "result")
    assert r.json()["ok"] is True
    assert json.loads(marks(home).read_text())[SID]["mark"] == "done"
    rows = {row["id"]: row for row in call(live.port, "GET", "/api/sessions").json()["sessions"]}
    assert (rows[SID]["done"], rows[SID]["manual_mark"], rows[SID]["group"]) == (True, "done", 4)
    assert runner.calls == []


def test_resume_opens_a_terminal_in_the_transcript_cwd(live: Live, home: Path, runner: Runner) -> None:
    validate("sessions", {"id": SID}, "resume_body")
    r = post(live, "resume", {"id": SID})
    assert r.status == 200
    validate("sessions", r.json(), "result")
    assert r.json()["ok"] is True
    launch = runner.calls[-1]
    assert launch[:3] == ("systemd-run", "--user", "--collect")
    assert "terminator" in launch
    assert f"--working-directory={CWD}" in launch
    assert "--setenv=DISPLAY=:7" in launch
    assert launch[-1] == f"claude --resume {SID}; exec zsh -i"


def test_resume_refuses_more_than_five_and_a_made_up_id(live: Live, home: Path, runner: Runner) -> None:
    many = post(live, "resume", {"ids": [SID] * 6})
    assert many.json()["refused"] is True
    made_up = post(live, "resume", {"id": "00000000-0000-4000-8000-000000000000"})
    assert made_up.json()["refused"] is True
    assert runner.calls == []


def test_delete_refuses_a_session_written_in_the_last_ten_minutes(
    live: Live, home: Path, runner: Runner
) -> None:
    path = home / "home/tester/.claude/projects/-home-tester-src-demo" / f"{OTHER}.jsonl"
    path.touch()
    r = post(live, "delete", {"id": OTHER})
    validate("sessions", r.json(), "result")
    assert r.json()["refused"] is True
    assert path.is_file()
    assert not (home / "home/tester/.claude/projects-trash").exists()


def test_delete_moves_an_old_session_to_the_trash(live: Live, home: Path, runner: Runner) -> None:
    r = post(live, "delete", {"ids": [OTHER]})
    assert r.json()["ok"] is True
    moved = list((home / "home/tester/.claude/projects-trash").rglob(f"{OTHER}.jsonl"))
    assert len(moved) == 1
    assert OTHER not in {row["id"] for row in call(live.port, "GET", "/api/sessions").json()["sessions"]}


@pytest.mark.parametrize("name", ["resume", "mark", "delete"])
@pytest.mark.parametrize("bad", DENIED, ids=["origin", "no-origin", "no-token", "bad-token"])
def test_a_post_without_the_origin_and_token_is_forbidden_and_changes_nothing(
    live: Live, home: Path, runner: Runner, name: str, bad: dict[str, str]
) -> None:
    before = sorted(str(p) for p in home.rglob("*"))
    r = post(live, name, {"ids": [OTHER], "mark": "done"}, **bad)
    assert r.status == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert runner.calls == []
    assert not marks(home).exists()
    assert sorted(str(p) for p in home.rglob("*")) == before


def test_bad_json_is_a_400_and_an_unknown_action_a_404(live: Live, home: Path, runner: Runner) -> None:
    assert post(live, "mark", "{oops").status == 400
    assert post(live, "nope", {}).status == 404
    assert post(live, "mark", "[1]").json()["ok"] is False
    assert runner.calls == []


def test_an_empty_body_is_refused_by_the_mutation_not_the_server(live: Live, home: Path) -> None:
    r = post(live, "delete")
    assert r.status == 200
    assert r.json()["ok"] is False


@pytest.mark.parametrize(
    ("fragment", "body"),
    [
        ("resume_body", {"ids": [SID] * 6}),
        ("resume_body", {}),
        ("mark_body", {"id": SID}),
        ("delete_body", {"id": SID, "ids": [SID]}),
    ],
)
def test_the_body_schemas_reject_what_the_server_refuses(fragment: str, body: dict[str, Any]) -> None:
    from jsonschema import ValidationError  # noqa: PLC0415

    with pytest.raises(ValidationError):
        validate("sessions", body, fragment)


def test_the_schema_accepts_the_shared_fixture() -> None:
    fixture = json.loads(
        (Path(__file__).parent.parent / "fixtures" / "sessions.json").read_text(encoding="utf-8")
    )
    validate("sessions", fixture)
