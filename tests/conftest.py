"""Every test launches turn hosts directly and never reads kuhy's real key, settings or SDK venv."""

import os
from pathlib import Path

import pytest
from todoimpl.apikey import cache
from todoimpl.relay.status import NOTIFY, STATUS


@pytest.fixture(autouse=True)
def _direct_turn_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_TURN_LAUNCH", "direct")


@pytest.fixture(autouse=True)
def _hold_the_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    """Rest runs at the gate as before T2060, so tests drive Ship by hand; tests of the new rule unset it."""
    monkeypatch.setenv("TODOIMPL_HOLD_GATE", "1")


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
    monkeypatch.delenv("TODOIMPL_CLAUDE", raising=False)  # a board session sets it to the real claude (T2055)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(empty / "claude"))  # no real OAuth token, no usage probe
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


@pytest.fixture(autouse=True)
def _no_real_free_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the cheap tier away from kuhy's real OmniRoute gateway (port 1 refuses)."""
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", "http://127.0.0.1:1")


@pytest.fixture(autouse=True)
def _no_real_umbrella_registry(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the umbrella registry at a missing temp file: kuhy's real list is never read."""
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(tmp_path_factory.mktemp("umbrellas") / "umbrellas.txt"))


@pytest.fixture(autouse=True)
def _no_real_gateway_secrets(
    tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Point the gateway key and dashboard password at an empty temp dir: kuhy's real ones are never read."""
    monkeypatch.setenv("TODOIMPL_OMNIROUTE_DIR", str(tmp_path_factory.mktemp("omniroute-secrets")))


@pytest.fixture(autouse=True)
def _network_is_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test opens a socket to the internet: the connectivity probe says yes unless a test flips it."""
    monkeypatch.setattr("todoimpl.runner.netwait.probe", lambda: True)


@pytest.fixture(autouse=True)
def _quick_deploy_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ship waits for a deploy host: look for its record every 20 ms, not every second."""
    monkeypatch.setattr("todoimpl.runner.deploy.POLL", 0.02)


@pytest.fixture(autouse=True)
def _no_real_build_lock(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the build lock, its shims and env files in a temp dir; no test starts out holding the lock."""
    monkeypatch.setenv("TODOIMPL_BUILD_ROOT", str(tmp_path_factory.mktemp("build-lock")))
    monkeypatch.delenv("TODOIMPL_BUILD_LOCK_HELD", raising=False)
    monkeypatch.delenv("TODOIMPL_BUILD_CARD", raising=False)


@pytest.fixture(autouse=True)
def _no_real_todo_images(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the todo images root at a missing temp dir: kuhy's real dufs folder is never read or written."""
    monkeypatch.setenv("TODOIMPL_IMAGES_ROOT", str(tmp_path_factory.mktemp("todo-images") / "missing"))


@pytest.fixture(autouse=True)
def _no_real_devices_file(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the paired-device list at a temp file: kuhy's real devices.json is never read or written."""
    monkeypatch.setenv("TODOIMPL_DEVICES", str(tmp_path_factory.mktemp("devices") / "devices.json"))


@pytest.fixture(autouse=True)
def _no_real_error_state(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the app-error state root at an empty temp dir: kartka's real state.json is never read."""
    monkeypatch.setenv("TODOIMPL_ERROR_STATE_ROOT", str(tmp_path_factory.mktemp("error-state")))


@pytest.fixture(autouse=True)
def _no_real_relay(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never start the phone relay against the real Firebase; each test starts healthy (relay, pinger)."""
    monkeypatch.delenv("TODOIMPL_RELAY", raising=False)
    STATUS.ok()
    NOTIFY.ok()


@pytest.fixture(autouse=True)
def _no_real_uploads(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> None:
    """Stage new-task attachments in a temp dir: kuhy's real `$TODOIMPL_HOME/uploads` is never touched."""
    monkeypatch.setenv("TODOIMPL_UPLOADS_ROOT", str(tmp_path_factory.mktemp("uploads")))
