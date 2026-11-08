"""Hermetic key tests: a temp HOME and key path; fake keys only, never a real one, never the real network."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "shims"))

from fake_todo_mcp import FakeTodoMcp


@pytest.fixture(autouse=True)
def home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.delenv("TODOIMPL_APIKEY", raising=False)
    return home


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server
