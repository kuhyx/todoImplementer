"""Hermetic runner world: temp HOME; fake claude, push-refusing git, pass-through capped.sh on PATH."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))

from collections.abc import Iterator

from runnerfakes import Env, make_env
from tierfakes import Free
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


@pytest.fixture
def free(world: Env, monkeypatch: pytest.MonkeyPatch) -> Iterator[Free]:
    """Free models reachable: a public repo and a gateway that answers (flip `public` / `up`)."""
    outside = Free(world)
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", outside.url)
    yield outside
    outside.stop()
