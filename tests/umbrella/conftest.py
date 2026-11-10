"""Fixtures: a fake todo MCP (JSON mode) and the shims dir on the path."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shims"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runner"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fake_todo_mcp import FakeTodoMcp
from runnerfakes import Env, make_env
from tierfakes import Free
from todoimpl.runner import retry
from todoimpl.todo_mcp.client import TodoClient


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture
def client(fake: FakeTodoMcp) -> TodoClient:
    return TodoClient(fake.url, fake.token)


@pytest.fixture(autouse=True)
def _fast_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(retry, "BACKOFF", (0.3, 0.3, 0.3))
    monkeypatch.setattr(retry, "LONG_WAIT", 0.3)


@pytest.fixture
def world(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Env:
    built, env = make_env(tmp_path)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    for key in ("TODOIMPL_CLAUDE", "TODOIMPL_MODEL", "TODOIMPL_SRC", "CLAUDECODE"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TODOIMPL_UMBRELLAS", str(tmp_path / "umbrellas.txt"))
    return built


@pytest.fixture
def free(world: Env, monkeypatch: pytest.MonkeyPatch) -> Iterator[Free]:
    outside = Free(world)
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", outside.url)
    yield outside
    outside.stop()
