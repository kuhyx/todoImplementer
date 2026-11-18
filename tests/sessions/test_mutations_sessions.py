from __future__ import annotations

import json
import pathlib
from typing import TYPE_CHECKING

import pytest
import sessfix as fx
from sessrunner import FakeRunner, ok
from todoimpl.sessions import api, mark, resume, router

if TYPE_CHECKING:
    from pathlib import Path

SHOW_ENV = ("systemctl", "--user", "show-environment")
EPOCH = 1792600000


@pytest.fixture(autouse=True)
def transcript(sysroot: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """One known session whose working directory exists under the test root."""
    monkeypatch.setattr(resume, "now", lambda: EPOCH + 0.7)
    monkeypatch.setattr(mark, "now", lambda: EPOCH + 0.7)
    (sysroot / fx.CWD.lstrip("/")).mkdir(parents=True)
    fx.write(fx.projects_dir(sysroot), fx.session("QUESTION: which?"))
    return sysroot / "home/tester/.claude/session-status.json"


def _argv(display: str, xauth: str) -> tuple[str, ...]:
    return (
        "systemd-run",
        "--user",
        "--collect",
        f"--unit=claude-resume-11111111-{EPOCH}",
        f"--setenv=DISPLAY={display}",
        f"--setenv=XAUTHORITY={xauth}",
        "terminator",
        f"--working-directory={fx.CWD}",
        "-x",
        "zsh",
        "-lic",
        f"claude --resume {fx.SID}; exec zsh -i",
    )


BAD_IDS = [
    None,
    {},
    {"id": 7},
    {"id": "not-a-uuid"},
    {"id": "; rm -rf ~"},
    # uuid.UUID() accepts all of these; only the canonical spelling is an id.
    {"id": fx.SID.replace("1", "A")},
    {"id": "{" + fx.SID + "}"},
    {"id": fx.SID.replace("-", "")},
]


@pytest.mark.parametrize("body", BAD_IDS)
def test_resume_refuses_a_bad_id(body: object) -> None:
    runner = FakeRunner({})
    result = resume.apply(runner, body)
    assert not result.ok
    assert runner.calls == []


def test_resume_refuses_an_unknown_id() -> None:
    runner = FakeRunner({})
    result = resume.apply(runner, {"id": fx.OTHER_SID})
    assert result.refused
    assert runner.calls == []


def test_resume_refuses_a_vanished_directory(sysroot: Path) -> None:
    (sysroot / fx.CWD.lstrip("/")).rmdir()
    runner = FakeRunner({})
    result = resume.apply(runner, {"id": fx.SID})
    assert not result.ok
    assert fx.CWD in result.summary
    assert runner.calls == []


def test_resume_launches_a_transient_terminal_unit() -> None:
    env = "HOME=/home/tester\nDISPLAY=:1\nXAUTHORITY=/run/x/auth\n"
    argv = _argv(":1", "/run/x/auth")
    runner = FakeRunner({SHOW_ENV: ok(SHOW_ENV, env), argv: ok(argv, "")})
    # cwd comes from the transcript, never from the request.
    result = resume.apply(runner, {"id": fx.SID, "cwd": "/etc"})
    assert result.ok, result
    assert runner.calls == [SHOW_ENV, argv]
    assert result.argv == argv


def test_resume_falls_back_to_default_display() -> None:
    argv = _argv(":0", "/home/tester/.Xauthority")
    runner = FakeRunner({argv: ok(argv, "")})
    assert resume.apply(runner, {"id": fx.SID}).ok
    assert runner.calls[-1] == argv


def test_resume_reports_a_failed_launch() -> None:
    result = resume.apply(FakeRunner({}), {"id": fx.SID})
    assert not result.ok
    assert not result.refused
    assert "no fixture" in result.stderr


def test_argv_builder_rejects_a_non_canonical_id() -> None:
    with pytest.raises(ValueError, match="canonical"):
        resume.build_argv("abc; reboot", "/x", ":0", "/x/.Xauthority", 1)


@pytest.mark.parametrize("body", BAD_IDS)
def test_mark_refuses_a_bad_id(body: object, transcript: Path) -> None:
    assert not mark.apply(FakeRunner({}), body).ok
    assert not transcript.exists()


def test_mark_refuses_an_unknown_id(transcript: Path) -> None:
    result = mark.apply(FakeRunner({}), {"id": fx.OTHER_SID, "mark": "done"})
    assert result.refused
    assert not transcript.exists()


@pytest.mark.parametrize("bad", ["finished", 1, True])
def test_mark_refuses_an_unknown_mark(bad: object, transcript: Path) -> None:
    result = mark.apply(FakeRunner({}), {"id": fx.SID, "mark": bad})
    assert not result.ok
    assert not transcript.exists()


def test_mark_done_then_clear(transcript: Path) -> None:
    transcript.parent.mkdir(parents=True, exist_ok=True)
    transcript.write_text(json.dumps({fx.OTHER_SID: {"mark": "done", "at": 1}}))
    assert mark.apply(FakeRunner({}), {"id": fx.SID, "mark": "done"}).ok
    stored = json.loads(transcript.read_text())
    assert stored == {
        fx.OTHER_SID: {"mark": "done", "at": 1},
        fx.SID: {"mark": "done", "at": EPOCH},
    }
    rows = api.listing(FakeRunner({}))["sessions"]
    assert rows[0]["done"] is True
    assert mark.apply(FakeRunner({}), {"id": fx.SID, "mark": None}).ok
    assert json.loads(transcript.read_text()) == {fx.OTHER_SID: {"mark": "done", "at": 1}}
    # No temp files left beside it: the write is tmp + rename.
    assert not list(transcript.parent.glob("*.tmp"))


@pytest.mark.parametrize("name", ["resume", "mark", "delete"])
def test_router_dispatches_session_mutations(name: str) -> None:
    payload = router.mutate(FakeRunner({}), name, {"id": "x"})
    assert payload is not None
    assert set(payload) == {"ok", "refused", "summary", "stdout", "stderr", "argv"}
    assert payload["ok"] is False


def test_show_environment_noise_is_ignored() -> None:
    argv = _argv(":2", "/home/tester/.Xauthority")
    env = "not an assignment\nDISPLAY=:2\n"
    runner = FakeRunner({SHOW_ENV: ok(SHOW_ENV, env), argv: ok(argv, "")})
    assert resume.apply(runner, {"id": fx.SID}).ok


def test_a_failed_mark_write_leaves_no_temp_file(transcript: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_src: str, _dst: object) -> None:
        msg = "read-only file system"
        raise OSError(msg)

    monkeypatch.setattr(pathlib.Path, "replace", refuse)
    result = mark.apply(FakeRunner({}), {"id": fx.SID, "mark": "done"})
    assert not result.ok
    assert "read-only" in result.stderr
    assert [p.name for p in transcript.parent.iterdir()] == ["projects"]
