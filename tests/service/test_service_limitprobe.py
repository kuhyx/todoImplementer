"""The board re-checks a held plan limit against the plan's real usage; build_backend starts the probe."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from servicefakes import FakeScheduler, Rig
from todoimpl.runner import limits
from todoimpl.service import build_backend
from todoimpl.todo_mcp.client import TodoClient
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from fake_todo_mcp import FakeTodoMcp

SOON = 4_000_000_000.0  # a limit far in the future


def test_t1882_a_board_request_lifts_a_limit_the_plan_no_longer_backs(rig: Rig) -> None:
    rig.note()
    probe = rig.backend.limit_probe
    assert probe is not None
    probe._fetch = lambda now: oauth.Probe(now, None, oauth.Window(0.03, SOON))
    probe._min_gap = 0.0
    limits.write_until(rig.root, SOON)
    assert rig.backend.board()["limit"]["active"] is True  # this response still shows the stored limit
    probe.join()
    board = rig.backend.board()
    assert board["limit"]["active"] is False
    assert rig.backend.usage()["limit"]["active"] is False


def test_build_backend_starts_the_probe_loop(
    fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen = threading.Event()

    def fetch(now: float) -> oauth.Probe:
        seen.set()
        return oauth.Probe(now, None, None)

    monkeypatch.setattr(oauth, "fetch", fetch)
    backend = build_backend(
        root=tmp_path, build="x", client=TodoClient(fake.url, fake.token), scheduler=FakeScheduler()
    )
    try:
        assert seen.wait(5)
    finally:
        assert backend.limit_probe is not None
        backend.limit_probe.stop()
        backend.cache.stop()
