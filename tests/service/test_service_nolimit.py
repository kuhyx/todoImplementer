"""The no-limit runner's row rides on /api/usage; build_backend starts its loop with the other watchers."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from contract_lib import validate
from servicefakes import FakeScheduler, Rig
from todoimpl.nolimit import status
from todoimpl.nolimit.tick import Loop
from todoimpl.service import build_backend
from todoimpl.todo_mcp.client import TodoClient

if TYPE_CHECKING:
    from pathlib import Path

    from fake_todo_mcp import FakeTodoMcp


def test_t2548_usage_carries_the_no_limit_row_and_validates(rig: Rig) -> None:
    usage = rig.backend.usage()
    validate("usage", usage)
    assert usage["nolimit"] == {"active": False, "repo": None, "result": None, "at": None}
    rig.root.mkdir(parents=True, exist_ok=True)
    status.set_active(rig.root, active=True)
    status.finish(rig.root, "kcd2-dice-solver", status.SLOW, 1_800_000_000.0)
    usage = rig.backend.usage()
    validate("usage", usage)
    assert usage["nolimit"] == {
        "active": True,
        "repo": "kcd2-dice-solver",
        "result": "slow",
        "at": 1_800_000_000.0,
    }
    assert json.loads((rig.root / status.FILE).read_text(encoding="utf-8"))["cycle"] == ["kcd2-dice-solver"]


def test_build_backend_starts_the_no_limit_loop(fake: FakeTodoMcp, tmp_path: Path) -> None:
    backend = build_backend(
        root=tmp_path, build="x", client=TodoClient(fake.url, fake.token), scheduler=FakeScheduler()
    )
    try:
        assert isinstance(backend.nolimit, Loop)
    finally:
        assert backend.nolimit is not None
        backend.nolimit.stop()
        for watcher in (backend.gateway, backend.limit_probe):
            assert watcher is not None
            watcher.stop()
        backend.cache.stop()
