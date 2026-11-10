"""The free-model gateway's cached reading rides on /api/usage; build_backend wires and starts its monitor."""

from __future__ import annotations

from typing import TYPE_CHECKING

from contract_lib import validate
from servicefakes import FakeScheduler, Rig
from todoimpl.gateway.monitor import GatewayMonitor
from todoimpl.service import build_backend
from todoimpl.todo_mcp.client import TodoClient

if TYPE_CHECKING:
    from pathlib import Path

    from fake_todo_mcp import FakeTodoMcp


def test_usage_has_no_free_object_without_a_gateway_monitor(rig: Rig) -> None:
    rig.backend.gateway = None
    assert "free" not in rig.backend.usage()


def test_usage_carries_the_cached_reading_and_validates(rig: Rig) -> None:
    rig.backend.gateway = GatewayMonitor(rig.root)
    usage = rig.backend.usage()  # never read: unknown, and nothing waited for the gateway
    validate("usage", usage)
    assert (usage["free"]["state"], usage["free"]["at"]) == ("unknown", None)


def test_build_backend_starts_the_gateway_monitor(fake: FakeTodoMcp, tmp_path: Path) -> None:
    backend = build_backend(
        root=tmp_path, build="x", client=TodoClient(fake.url, fake.token), scheduler=FakeScheduler()
    )
    try:
        assert isinstance(backend.gateway, GatewayMonitor)
        assert backend.gateway._thread is not None
    finally:
        assert backend.gateway is not None
        backend.gateway.stop()
        assert backend.limit_probe is not None
        backend.limit_probe.stop()
        backend.cache.stop()
