"""build_backend: defaults, scheduler import, startup with the todo app down."""

import sys
import types
from pathlib import Path
from typing import Any

import pytest
from fake_todo_mcp import FakeTodoMcp
from servicefakes import FakeScheduler
from todoimpl.http.backend import BackendError
from todoimpl.service import ItemView, build_backend
from todoimpl.todo_mcp.client import TodoClient


def test_defaults_come_from_the_environment(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = tmp_path / "token"
    token.write_text(fake.token, encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_MCP_URL", fake.url)
    monkeypatch.setenv("TODOIMPL_MCP_TOKEN_FILE", str(token))
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "home"))
    fake.seed("kuhyx/demo", "demo todos", "")
    backend = build_backend(scheduler=FakeScheduler())
    try:
        assert backend.root == tmp_path / "home"
        assert len(backend.board()["tasks"]) == 1
        assert backend.build
    finally:
        backend.cache.stop()


def test_scheduler_is_imported_lazily_and_gets_the_item_view(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: dict[str, Any] = {}

    class Scheduler(FakeScheduler):
        def __init__(self, client: object, root: Path) -> None:
            super().__init__()
            seen.update(client=client, root=root)

    module = types.ModuleType("todoimpl.runner.scheduler")
    module.Scheduler = Scheduler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "todoimpl.runner.scheduler", module)
    backend = build_backend(root=tmp_path, build="x", client=TodoClient(fake.url, fake.token), refresh=False)
    assert isinstance(seen["client"], ItemView)
    assert seen["root"] == tmp_path
    assert backend.build == "x"


def test_startup_survives_a_dead_todo_app_and_the_board_says_why(tmp_path: Path) -> None:
    backend = build_backend(
        root=tmp_path, build="x", client=TodoClient("http://127.0.0.1:1/mcp", "t"), scheduler=FakeScheduler()
    )
    try:
        with pytest.raises(BackendError, match="cannot reach MCP server") as err:
            backend.board()
        assert err.value.code == "upstream_unavailable"
    finally:
        backend.cache.stop()


def test_t901_scheduler_recovery_can_read_the_notes_at_construction(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The engine's first act (recover -> drive -> get_task) must not race the first note fetch."""
    card = f"{fake.seed('kuhyx/demo', 'demo todos', '')[:8]}-0"
    seen: dict[str, object] = {}

    class Scheduler(FakeScheduler):
        def __init__(self, client: ItemView, root: Path) -> None:
            super().__init__()
            seen["card"] = client.get_task(card).id

    module = types.ModuleType("todoimpl.runner.scheduler")
    module.Scheduler = Scheduler  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "todoimpl.runner.scheduler", module)
    backend = build_backend(root=tmp_path, build="x", client=TodoClient(fake.url, fake.token))
    backend.cache.stop()
    assert seen == {"card": card}
