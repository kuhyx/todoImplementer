"""Fixtures: a fake todo MCP server in both reply modes; makes tests/shims importable."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "shims"))

from fake_todo_mcp import FakeTodoMcp
from todoimpl.todo_mcp.client import TodoClient


@pytest.fixture(params=[False, True], ids=["json", "sse"])
def fake(request: pytest.FixtureRequest) -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp(sse=request.param) as server:
        yield server


@pytest.fixture
def client(fake: FakeTodoMcp) -> TodoClient:
    return TodoClient(fake.url, fake.token)
