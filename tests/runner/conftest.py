"""Hermetic runner world: temp HOME; fake claude, push-refusing git, pass-through capped.sh on PATH."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runnerfakes import Env, make_env
from todoimpl.runner import retry


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """Retry waits of minutes become tenths of a second; the real values are retry.DEFAULT_*."""
    monkeypatch.setattr(retry, "BACKOFF", (0.3, 0.3, 0.3))
    monkeypatch.setattr(retry, "LONG_WAIT", 0.3)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    built, env = make_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("TODOIMPL_CLAUDE", "TODOIMPL_MODEL", "TODOIMPL_SRC", "CLAUDECODE"):
        monkeypatch.delenv(key, raising=False)
    return built
