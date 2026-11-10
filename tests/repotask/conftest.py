"""Fixtures: a fake todo MCP and a hermetic world (fake claude, remotes, run root) for repo-task flows."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shims"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_todo_mcp import FakeTodoMcp
from repofakes import Rig, build_rig
from runnerfakes import Env, make_env
from todoimpl.runner import retry


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "BACKOFF", (0.3, 0.3, 0.3))
    monkeypatch.setattr(retry, "LONG_WAIT", 0.3)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    built, env = make_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("TODOIMPL_CLAUDE", "TODOIMPL_MODEL", "CLAUDECODE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TODOIMPL_SRC", str(built.src))
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(tmp_path / "umbrellas.txt"))
    return built


@pytest.fixture
def rig(world: Env, fake: FakeTodoMcp) -> Iterator[Rig]:
    built = build_rig(world, fake)
    yield built
    built.sched.close()
