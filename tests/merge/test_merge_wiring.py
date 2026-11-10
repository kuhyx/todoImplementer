"""The merge service is wired into build_backend, found by the router and kicked once at server start."""

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from fake_todo_mcp import FakeTodoMcp
from mergefakes import Rig
from todoimpl.http import main as http_main
from todoimpl.http.app import make_server
from todoimpl.http.merge import MergeApi
from todoimpl.merge.service import MergeService
from todoimpl.service import build_backend
from todoimpl.todo_mcp.client import TodoClient


def test_build_backend_carries_a_merge_service(fake: FakeTodoMcp, tmp_path: Path) -> None:
    backend = build_backend(
        root=tmp_path,
        build="x",
        client=TodoClient(fake.url, fake.token),
        scheduler=MagicMock(),
        refresh=False,
    )
    assert isinstance(backend.merge_service, MergeService)
    assert isinstance(backend.merge_service, MergeApi)
    assert backend.merge_service.root == tmp_path


def test_router_serves_the_merge_routes_of_a_service_backend(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(MergeService, "refresh_if_due", lambda _self: False)
    backend = build_backend(
        root=tmp_path,
        build="x",
        client=TodoClient(fake.url, fake.token),
        scheduler=MagicMock(),
        refresh=False,
    )
    server = make_server(backend, port=0, dist=tmp_path, build="b1")
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
    thread.start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}/api/merges"
        with urllib.request.urlopen(url, timeout=5) as reply:
            assert json.load(reply) == {"suggestions": []}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


def test_main_kicks_the_classification_once_at_start(rig: Rig, monkeypatch: pytest.MonkeyPatch) -> None:
    kicks: list[str] = []

    class Backend:
        merge_service = type("M", (), {"refresh_if_due": lambda _self: kicks.append("kick")})()

    served: list[Any] = []
    monkeypatch.setattr(http_main, "load_backend", Backend)
    monkeypatch.setattr(http_main, "serve", lambda backend, *_a, **_k: served.append(backend))
    assert http_main.main([]) == 0
    assert kicks == ["kick"]
    assert len(served) == 1


def test_main_without_a_merge_service_just_serves(monkeypatch: pytest.MonkeyPatch) -> None:
    served: list[Any] = []
    monkeypatch.setattr(http_main, "load_backend", object)
    monkeypatch.setattr(http_main, "serve", lambda backend, *_a, **_k: served.append(backend))
    assert http_main.main([]) == 0
    assert len(served) == 1
