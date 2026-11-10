"""The monitor: reads off the request path, keeps the last good reading, says why it is old or down."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest
from gatewayfakes import MASKED, NOW, Gateway, wait_for
from todoimpl.gateway.client import Client
from todoimpl.gateway.monitor import INTERVAL, REDISCOVER, STALE_AFTER, GatewayMonitor
from todoimpl.umbrella import workers


class Clock:
    def __init__(self) -> None:
        self.now = NOW

    def __call__(self) -> float:
        return self.now


def monitor(root: Path, clock: Clock | None = None) -> GatewayMonitor:
    return GatewayMonitor(root, clock=clock or Clock())


def test_before_the_first_read_the_view_is_unknown_and_asks_nothing(gateway: Gateway, tmp_path: Path) -> None:
    view = monitor(tmp_path).view()
    assert (view["state"], view["at"], view["error"]) == ("unknown", None, None)
    assert view["providers"] == []
    assert view["tokens"] is None
    assert gateway.requests == []


def test_a_read_fills_the_view_and_viewing_never_calls_the_gateway(gateway: Gateway, tmp_path: Path) -> None:
    mon = monitor(tmp_path)
    mon.refresh()
    asked = len(gateway.requests)
    view = mon.view()
    assert (view["state"], view["at"], view["error"]) == ("ok", NOW, None)
    assert view["counts"]["providers"] == 5
    assert view["quotas"][0]["provider"] == "openrouter"
    assert view["tokens"]["requests"] == 163
    assert len(gateway.requests) == asked


def test_the_view_never_carries_a_secret(gateway: Gateway, tmp_path: Path) -> None:
    mon = monitor(tmp_path)
    mon.refresh()
    text = json.dumps(mon.view())
    assert MASKED not in text
    assert "pw-secret" not in text
    assert "sk-fake" not in text


def test_only_providers_with_a_quota_are_asked_again(gateway: Gateway, tmp_path: Path) -> None:
    mon = monitor(tmp_path)
    mon.refresh()
    first = [p for p, _ in gateway.requests if p.startswith("/api/usage/id-")]
    gateway.requests.clear()
    mon.refresh()
    again = [p for p, _ in gateway.requests if p.startswith("/api/usage/id-")]
    assert len(first) == 5
    assert again == ["/api/usage/id-openrouter"]


def test_every_so_often_all_providers_are_scanned_again(gateway: Gateway, tmp_path: Path) -> None:
    mon = monitor(tmp_path)
    for _ in range(REDISCOVER + 1):
        mon.refresh()
    scans = [p for p, _ in gateway.requests if p == "/api/usage/id-nvidia"]
    assert len(scans) == 2  # the first read and the REDISCOVERth


def test_ours_counts_the_tokens_of_calls_made_while_our_workers_ran(gateway: Gateway, tmp_path: Path) -> None:
    run_dir = tmp_path / "abcd1234-0"
    workers.record(run_dir, {"child": "kuhyx/a", "attempt": 1, "start": NOW - 30, "end": NOW, "exit": 0})
    workers.record(run_dir, {"child": "kuhyx/a", "attempt": 1, "start": 5.0, "end": 6.0, "exit": 0})
    workers.record(run_dir, {"child": "kuhyx/a", "attempt": 1, "start": "x", "end": None})
    mon = monitor(tmp_path)
    mon.refresh()
    assert mon.view()["tokens"]["ours"] == 1010  # the 1970 attempt is not today's


def test_no_workers_today_means_ours_is_unknown(gateway: Gateway, tmp_path: Path) -> None:
    mon = monitor(tmp_path)
    mon.refresh()
    assert mon.view()["tokens"]["ours"] is None


def test_a_section_that_fails_is_named_and_the_rest_still_shows(gateway: Gateway, tmp_path: Path) -> None:
    del gateway.answers["/api/combos"]
    mon = monitor(tmp_path)
    mon.refresh()
    view = mon.view()
    assert view["state"] == "ok"
    assert view["error"] == "combos: HTTP 400"
    assert view["combo"] is None
    assert view["counts"]["providers"] == 5


def test_a_dead_gateway_keeps_the_last_reading_flagged_down(gateway: Gateway, tmp_path: Path) -> None:
    clock = Clock()
    mon = monitor(tmp_path, clock)
    mon.refresh()
    gateway.stop()
    clock.now += 10
    mon.refresh()
    view = mon.view()
    assert view["state"] == "down"
    assert view["at"] == NOW  # the age of what is shown
    assert "unreachable" in str(view["error"])
    assert view["counts"]["providers"] == 5


def test_a_gateway_that_was_never_read_is_down_not_unknown(tmp_path: Path, secrets: Path) -> None:
    mon = GatewayMonitor(tmp_path, client=Client("http://127.0.0.1:1"), clock=Clock())
    mon.refresh()
    assert mon.view()["state"] == "down"


def test_an_old_reading_is_stale(gateway: Gateway, tmp_path: Path) -> None:
    clock = Clock()
    mon = monitor(tmp_path, clock)
    mon.refresh()
    clock.now += STALE_AFTER * INTERVAL + 1
    assert mon.view()["state"] == "stale"


def test_a_crash_inside_the_loop_is_logged_not_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    mon = monitor(tmp_path)

    def boom() -> None:
        raise RuntimeError

    monkeypatch.setattr(mon, "refresh", boom)
    with caplog.at_level(logging.ERROR, logger="todoimpl.gateway"):
        mon._safe_refresh()
    assert "gateway refresh crashed" in caplog.text


def test_the_loop_reads_in_the_background_and_stops(gateway: Gateway, tmp_path: Path) -> None:
    mon = GatewayMonitor(tmp_path, clock=Clock(), interval=0.05)
    mon.start()
    mon.start()  # idempotent
    wait_for(lambda: mon.view()["state"] == "ok")
    mon.stop()
    asked = len(gateway.requests)
    wait_for(lambda: True)
    assert len(gateway.requests) == asked
    GatewayMonitor(tmp_path).stop()  # stopping one that never started is fine
