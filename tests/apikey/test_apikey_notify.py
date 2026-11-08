import logging
import stat
from pathlib import Path

import pytest
from todoimpl.apikey.notify import notify_send


def shim(directory: Path, code: int = 0) -> Path:
    directory.mkdir(exist_ok=True)
    path = directory / "notify-send"
    path.write_text(f'#!/bin/sh\nprintf "%s|" "$@" > "{directory}/args"\nexit {code}\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def test_sends_title_and_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shim(tmp_path / "bin")
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert notify_send("T", "body") is True
    assert (tmp_path / "bin" / "args").read_text() == "-u|critical|T|body|"


def test_missing_notify_send_is_skipped_but_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv("PATH", str(tmp_path))
    with caplog.at_level(logging.WARNING):
        assert notify_send("T", "b") is False
    assert "notify-send" in caplog.text


def test_failing_notify_send_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    shim(tmp_path / "bin", code=1)
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    with caplog.at_level(logging.WARNING):
        assert notify_send("T", "b") is False
    assert "exit 1" in caplog.text
