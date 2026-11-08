"""scripts/rotate_api_key.py real seams (xclip, xdg-open, TTY, clock) with fakes standing in for the tools."""

import getpass
import runpy
import shutil
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
import rotate_api_key as rot
from todoimpl.apikey.verify import urllib_transport

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "rotate_api_key.py"


class FakeRun:
    def __init__(self, stdout: bytes = b"", code: int = 0, *, error: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], dict[str, Any]]] = []
        self.stdout, self.code, self.error = stdout, code, error

    def __call__(self, argv: list[str], **kw: Any) -> subprocess.CompletedProcess[bytes]:
        self.calls.append((argv, kw))
        if self.error is not None:
            raise self.error
        return subprocess.CompletedProcess(argv, self.code, self.stdout, b"")


def test_real_clipboard_reader_uses_xclip(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun(b"hello\n")
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/xclip")
    monkeypatch.setattr(subprocess, "run", run)
    assert rot.read_clipboard() == "hello\n"
    assert run.calls[0][0] == ["xclip", "-o", "-selection", "clipboard"]


def test_real_clipboard_reader_edge_cases(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    assert rot.read_clipboard() is None
    monkeypatch.setattr(shutil, "which", lambda _name: "/fake/xclip")
    for fake in (
        FakeRun(code=1),
        FakeRun(error=subprocess.TimeoutExpired("xclip", 5)),
        FakeRun(error=OSError()),
    ):
        monkeypatch.setattr(subprocess, "run", fake)
        assert rot.read_clipboard() == ""


def test_real_clipboard_clear_empties_the_selection(monkeypatch: pytest.MonkeyPatch) -> None:
    run = FakeRun()
    monkeypatch.setattr(subprocess, "run", run)
    rot.clear_clipboard()
    argv, kw = run.calls[0]
    assert argv == ["xclip", "-selection", "clipboard"]
    assert kw["input"] == b""
    monkeypatch.setattr(subprocess, "run", FakeRun(error=OSError()))
    rot.clear_clipboard()  # a missing xclip is not an error


def test_real_opener_detaches_xdg_open(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[tuple[list[str], dict[str, Any]]] = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: started.append((argv, kw)))
    rot.open_url("https://example.invalid/x")
    assert started[0][0] == ["xdg-open", "https://example.invalid/x"]
    assert started[0][1]["start_new_session"] is True

    def missing(*_a: Any, **_k: Any) -> None:
        raise OSError

    monkeypatch.setattr(subprocess, "Popen", missing)
    rot.open_url("https://example.invalid/x")  # no xdg-open: the instruction line still names the URL


def test_real_io_wires_the_real_functions(monkeypatch: pytest.MonkeyPatch) -> None:
    io = rot.real_io()
    assert io.read_secret is getpass.getpass
    assert io.read_clipboard is rot.read_clipboard
    assert io.transport is urllib_transport
    assert io.today() == datetime.now().astimezone().date()
    monkeypatch.setattr("builtins.input", lambda _prompt: "skip")
    assert io.ask("x") == "skip"


def test_script_runs_as_main(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.argv", ["rotate_api_key.py", "--help"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(SCRIPT), run_name="__main__")
    assert stop.value.code == 0
