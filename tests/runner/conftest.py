"""Hermetic runner world: temp HOME; fake claude, push-refusing git, pass-through capped.sh on PATH."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from runnerfakes import Env, make_env


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    built, env = make_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("TODOIMPL_CLAUDE", "TODOIMPL_MODEL", "TODOIMPL_SRC", "CLAUDECODE"):
        monkeypatch.delenv(key, raising=False)
    return built
