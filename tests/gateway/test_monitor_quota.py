"""A provider that answers its usage call without a quota record is not a quota."""

from __future__ import annotations

from pathlib import Path

from gatewayfakes import NOW, Gateway
from todoimpl.gateway.monitor import GatewayMonitor


def test_a_provider_that_answers_without_quotas_is_no_quota(gateway: Gateway, tmp_path: Path) -> None:
    gateway.answers["/api/usage/id-nvidia"] = {"message": "balance not available"}
    mon = GatewayMonitor(tmp_path, clock=lambda: NOW)
    mon.refresh()
    assert [q["provider"] for q in mon.view()["quotas"]] == ["openrouter"]
