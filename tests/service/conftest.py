"""A fake todo MCP, a fake Scheduler and a ServiceBackend wired to both under a temp run root."""

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shims"))

from fake_todo_mcp import FakeTodoMcp  # noqa: E402
from servicefakes import FakeScheduler, Rig  # noqa: E402
from todoimpl.service import ServiceBackend, build_backend  # noqa: E402
from todoimpl.todo_mcp.client import TodoClient  # noqa: E402


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture
def rig(fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Rig]:
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "src"))
    scheduler = FakeScheduler()
    backend: ServiceBackend = build_backend(
        root=tmp_path / "run",
        build="b1",
        client=TodoClient(fake.url, fake.token),
        scheduler=scheduler,
        refresh=False,
    )
    yield Rig(fake, backend, scheduler, tmp_path / "run")
    backend.cache.stop()
