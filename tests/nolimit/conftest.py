"""A hermetic world for the no-limit runner: temp HOME, src root and run root, local bare remotes, shims."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from runnerfakes import Env, make_env


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    built, env = make_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("TODOIMPL_SRC", str(built.src))
    monkeypatch.delenv("CLAUDECODE", raising=False)
    return built
