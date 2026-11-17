"""Snap nodes are written only on change, rev only moves forward, the board seam sees each change."""

import asyncio
import logging
from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import ROOT
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import publisher as publisher_mod
from todoimpl.relay import worker
from todoimpl.relay.publisher import Publisher


class StopLoopError(Exception):
    pass


def run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_start_keeps_counters_and_writes_meta(fake: FakeRtdb) -> None:
    fake.set(f"{ROOT}/rev", {"board": 5, "usage": True, "sessions": -1, "merges": 2})

    async def go() -> dict[str, int]:
        db = fake.rtdb()
        pub = Publisher(db, {})
        await pub.start()
        await db.aclose()
        return pub.rev

    assert run(go()) == {"board": 5, "usage": 0, "sessions": 0, "merges": 2}
    assert fake.get(f"{ROOT}/meta") == {"min_client": 1, "schema": 1}


def test_publish_only_on_change_and_the_board_seam(fake: FakeRtdb, caplog: pytest.LogCaptureFixture) -> None:
    board = {"tasks": [1]}
    seen: list[tuple[Any, Any]] = []

    async def on_board(old: Any, new: Any) -> None:
        seen.append((old, new))

    def broken() -> dict[str, Any]:
        raise OSError("disk")

    async def go() -> list[bool]:
        db = fake.rtdb()
        pub = Publisher(db, {"board": lambda: dict(board), "usage": broken}, on_board=on_board)
        out = [await pub.publish("board"), await pub.publish("board")]
        board["tasks"] = [2]
        out += [
            await pub.publish("board"),
            await pub.publish("board", force=True),
            await pub.publish("usage"),
        ]
        await pub.refresh_all()
        await db.aclose()
        return out

    with caplog.at_level(logging.WARNING, logger="todoimpl.relay"):
        assert run(go()) == [True, False, True, True, False]
    assert fake.get(f"{ROOT}/snap/board") == {"tasks": [2]}
    assert fake.get(f"{ROOT}/rev/board") == 4
    assert seen[:2] == [(None, {"tasks": [1]}), ({"tasks": [1]}, {"tasks": [2]})]
    assert "cannot read usage" in caplog.text


def test_run_polls_each_node_on_its_interval(fake: FakeRtdb, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(publisher_mod, "INTERVALS", {"board": 1.0})
    clock = [0.0]
    reads: list[float] = []

    async def sleep(seconds: float) -> None:
        clock[0] += seconds
        if clock[0] > 2.1:
            raise StopLoopError

    def board() -> dict[str, Any]:
        reads.append(clock[0])
        return {"n": len(reads)}

    async def go() -> None:
        db = fake.rtdb()
        pub = Publisher(
            db,
            {"board": board},
            sleep=sleep,
            clock=lambda: clock[0],
        )
        with pytest.raises(StopLoopError):
            await pub.run()
        await db.aclose()

    run(go())
    assert reads == [0.0, 1.0, 2.0]


def test_sources_read_the_router(router: Router, backend: FakeBackend) -> None:
    found = worker.sources(router)
    assert set(found) == {"board", "usage", "sessions", "merges"}
    assert found["board"]() == backend.board_data
