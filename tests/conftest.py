"""Every test launches turn hosts directly and never reads kuhy's real key, settings or SDK venv."""

import os
from pathlib import Path

import pytest
from todoimpl.apikey import cache


@pytest.fixture(autouse=True)
def _direct_turn_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_TURN_LAUNCH", "direct")


@pytest.fixture(autouse=True)
def _no_real_credits_inputs(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point setting, key and SDK venv at an empty temp dir; start with the cached key status unknown."""
    empty: Path = tmp_path_factory.mktemp("credits-inputs")
    monkeypatch.setenv("TODOIMPL_SETTINGS", str(empty / "settings.json"))
    monkeypatch.setenv("TODOIMPL_APIKEY", str(empty / "anthropic_api_key"))
    monkeypatch.setenv("TODOIMPL_SDK_VENV", str(empty / "sdk-venv"))
    monkeypatch.delenv("TODOIMPL_SDK_PYTHON", raising=False)
    cache.put(None)


@pytest.fixture(autouse=True)
def _no_real_desktop_notifications(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Put a silent notify-send shim first on PATH so no test pops a notification on the real desktop."""
    shims: Path = tmp_path_factory.mktemp("notify-shim")
    shim = shims / "notify-send"
    shim.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shims}:{os.environ.get('PATH', '')}")
