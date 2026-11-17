"""A fake todo MCP, the real service backend over it, and a scheduler that records starts."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "service"))
sys.path.insert(0, str(HERE.parent / "shims"))

from errfakes import RunningScheduler  # noqa: E402
from fake_todo_mcp import FakeTodoMcp  # noqa: E402
from loopfakes import World  # noqa: E402
from servicefakes import Rig  # noqa: E402
from todoimpl.service import ServiceBackend, build_backend  # noqa: E402
from todoimpl.todo_mcp.client import TodoClient  # noqa: E402


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture
def rig(fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "src"))
    scheduler = RunningScheduler(tmp_path / "run")
    backend: ServiceBackend = build_backend(
        root=tmp_path / "run",
        build="b1",
        client=TodoClient(fake.url, fake.token),
        scheduler=scheduler,
        refresh=False,
    )
    yield Rig(fake, backend, scheduler, tmp_path / "run")
    backend.cache.stop()


@pytest.fixture
def world(rig: Rig, fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> World:
    monkeypatch.setattr("todoimpl.errors.settle.repo_dir", lambda _repo: tmp_path)  # a clone of kartka exists
    return World(rig, fake, tmp_path)
