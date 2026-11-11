"""The credits package: setting, marks, errors, sdk lookup, route decision."""

from __future__ import annotations

import json
import os
import sys
from datetime import date
from typing import TYPE_CHECKING

import pytest
from todoimpl.apikey import cache
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.credits import errors, marks, route, sdk, setting

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_793_880_000.0
KEY = "sk-ant-api03-" + "x" * 30


@pytest.fixture
def ready(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a root with an active plan limit, a usable key and an SDK python."""
    (tmp_path / "limit-until").write_text(str(NOW + 600))
    key = tmp_path / "key"
    key.write_text(KEY)
    monkeypatch.setenv("TODOIMPL_APIKEY", str(key))
    monkeypatch.setenv("TODOIMPL_SDK_PYTHON", sys.executable)
    cache.put(KeyStatus("ok", date(2026, 12, 1), "fine"))
    return tmp_path


def test_setting_defaults_on_and_persists_off_and_on() -> None:
    assert setting.enabled() is True
    setting.set_enabled(value=False)
    assert setting.enabled() is False
    setting.set_enabled(value=True)
    assert setting.enabled() is True


@pytest.mark.parametrize("text", ["{broken", "[1]", '{"credits_fallback": "no"}'])
def test_setting_garbage_means_the_default_on(text: str) -> None:
    path = setting.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    assert setting.enabled() is True


def test_setting_keeps_other_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    path = tmp_path / "s.json"
    path.write_text('{"other": 1}')
    monkeypatch.setenv("TODOIMPL_SETTINGS", str(path))
    setting.set_enabled(value=False)
    assert json.loads(path.read_text()) == {"other": 1, "credits_fallback": False}


def test_setting_path_defaults_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("TODOIMPL_SETTINGS")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert setting.settings_path() == tmp_path / ".config" / "todoImplementer" / "settings.json"


def test_exhausted_marker_holds_until_its_time_and_clears(tmp_path: Path) -> None:
    assert not marks.exhausted(tmp_path, NOW)
    marks.mark_exhausted(tmp_path, NOW + 10, "Credit balance is too low")
    assert marks.exhausted(tmp_path, NOW)
    assert not marks.exhausted(tmp_path, NOW + 11)
    marks.clear_exhausted(tmp_path)
    assert not marks.exhausted(tmp_path, NOW)
    (tmp_path / marks.EXHAUSTED_FILE).write_text("[1]")
    assert not marks.exhausted(tmp_path, NOW)


def test_alert_is_active_until_its_end(tmp_path: Path) -> None:
    assert marks.active_alert(tmp_path, NOW) is None
    marks.raise_alert(tmp_path, "stopped", NOW + 5)
    assert marks.active_alert(tmp_path, NOW) == {"kind": "overage", "text": "stopped", "until": NOW + 5}
    assert marks.active_alert(tmp_path, NOW + 6) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Credit balance is too low", True),
        ("API Error: 400 billing_error", True),
        ("invalid x-api-key", True),
        ("API Error: 529 overloaded", False),
        ("", False),
    ],
)
def test_exhausted_text(text: str, expected: bool) -> None:
    assert errors.exhausted(text) is expected


def test_sdk_python_is_found_by_env_or_venv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    assert sdk.python() is None
    venv = tmp_path / "venv"
    (venv / "bin").mkdir(parents=True)
    python = venv / "bin" / "python"
    python.write_text("#!/bin/sh\n")
    monkeypatch.setenv("TODOIMPL_SDK_VENV", str(venv))
    assert sdk.python() is None  # not executable
    python.chmod(0o755)
    assert sdk.python() == python
    monkeypatch.delenv("TODOIMPL_SDK_VENV")
    monkeypatch.setenv("HOME", str(tmp_path))
    assert sdk.venv_dir() == tmp_path / ".local" / "share" / "todoImplementer" / "sdk-venv"
    monkeypatch.setenv("TODOIMPL_SDK_PYTHON", sys.executable)
    assert sdk.python() == type(python)(sys.executable)
    assert os.access(sys.executable, os.X_OK)


def test_t1850_credits_only_when_limit_active_setting_on_and_key_usable(ready: Path) -> None:
    assert route.choose(ready, NOW) == route.Choice(route.CREDITS)
    assert route.choose(ready, NOW + 601) == route.Choice(
        route.CREDITS
    )  # no limit: paced credits all the same
    assert route.view(ready, NOW)["state"] == "ready"


def test_each_missing_condition_holds_the_run(ready: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    held = route.Choice(None, NOW + 600)
    setting.set_enabled(value=False)
    assert route.choose(ready, NOW) == held
    off = route.view(ready, NOW)
    assert (off["enabled"], off["state"], off["text"], off["route"]) == (False, "off", route.OFF_TEXT, None)
    setting.set_enabled(value=True)
    cache.put(KeyStatus("expired", date(2026, 11, 1), "expired on 2026-11-01"))
    assert route.choose(ready, NOW) == held
    assert "expired" in route.view(ready, NOW)["text"]
    cache.put(KeyStatus("ok", None, "fine"))
    marks.mark_exhausted(ready, NOW + 600, "x")
    assert route.choose(ready, NOW) == held
    assert route.view(ready, NOW)["state"] == "exhausted"
    marks.clear_exhausted(ready)
    monkeypatch.delenv("TODOIMPL_SDK_PYTHON")
    assert route.choose(ready, NOW) == held
    assert route.view(ready, NOW)["text"] == sdk.MISSING


def test_before_the_first_key_check_a_readable_key_counts(ready: Path) -> None:
    cache.put(None)
    assert route.choose(ready, NOW).route == route.CREDITS
    (ready / "key").write_text("")
    assert route.choose(ready, NOW).route is None
    assert "no API key" in route.view(ready, NOW)["text"]
