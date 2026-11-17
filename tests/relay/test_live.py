"""live_watch mirrors a card's feed while watched, keeps the newest events, and stops when nobody watches."""

import asyncio
import logging
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import DEV, ROOT
from rtdb_relay.server import RequestError
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import live as live_mod
from todoimpl.relay.live import Live


async def mirror_done(lv: Live, card: str) -> None:
    task = lv.mirrors.get(card)
    if task is not None:
        await asyncio.wait_for(task, 5)


def test_feed_lands_in_order_and_old_events_go(
    fake: FakeRtdb, router: Router, backend: FakeBackend, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(live_mod, "KEEP", 2)
    backend.events = [{"type": "activity", "seq": 1}, {"type": "activity", "seq": 2}]
    card = backend.task_id

    async def go() -> None:
        db = fake.rtdb()
        lv = Live(db, router)
        assert await lv.watch(DEV, card) == {}
        await mirror_done(lv, card)
        assert card not in lv.mirrors
        await lv.watch(DEV, None)
        await db.aclose()

    asyncio.run(go())
    feed = fake.get(f"{ROOT}/live/{card}")
    assert sorted(feed) == ["s000000002", "s000000003"]  # the stage snapshot was s000000001
    assert feed["s000000003"]["seq"] == 2
    assert fake.get(f"{ROOT}/watch/{DEV}") is None


def test_unknown_card_is_refused(fake: FakeRtdb, router: Router) -> None:
    async def go() -> None:
        db = fake.rtdb()
        try:
            await Live(db, router).watch(DEV, "zzzz9999-0")
        finally:
            await db.aclose()

    with pytest.raises(RequestError) as err:
        asyncio.run(go())
    assert err.value.code == "not_found"


def test_a_quiet_feed_stops_once_the_watch_lapses(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    clock = [time.time()]

    def slow(id8: str) -> Iterator[dict[str, Any]]:
        while True:
            time.sleep(0.05)
            yield {"type": "cost", "id": id8}

    backend.subscribe = slow  # type: ignore[method-assign]
    card = backend.task_id

    async def go() -> None:
        db = fake.rtdb()
        lv = Live(db, router, now=lambda: clock[0])
        lv.poll = 0.01
        await lv.watch(DEV, card)
        await lv.watch("other-dev", card)  # a second watcher shares the running mirror
        assert len(lv.mirrors) == 1
        await asyncio.sleep(0.2)
        clock[0] += 1000  # both watches lapse
        await mirror_done(lv, card)
        await db.aclose()

    asyncio.run(go())
    assert len(fake.get(f"{ROOT}/live/{card}")) >= 2


def test_a_failing_write_ends_the_mirror_loudly(
    fake: FakeRtdb, router: Router, backend: FakeBackend, caplog: pytest.LogCaptureFixture
) -> None:
    card = backend.task_id

    async def go() -> None:
        db = fake.rtdb()
        lv = Live(db, router)
        await lv.watch(DEV, card)

        async def broken(path: str, value: object) -> object:
            raise OSError("down")

        db.put = broken  # type: ignore[method-assign]
        await mirror_done(lv, card)
        await db.aclose()

    with caplog.at_level(logging.ERROR, logger="todoimpl.relay"):
        asyncio.run(go())
    assert "live mirror" in caplog.text


def test_pump_survives_a_closed_loop() -> None:
    loop = asyncio.new_event_loop()
    loop.close()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    live_mod._pump(iter([{"a": 1}]), queue, loop, threading.Event())


def test_pump_stops_when_told() -> None:
    loop = asyncio.new_event_loop()
    stop = threading.Event()
    stop.set()
    queue: asyncio.Queue[Any] = asyncio.Queue()
    live_mod._pump(iter([{"a": 1}]), queue, loop, stop)
    loop.run_until_complete(asyncio.sleep(0))
    assert queue.get_nowait() is None
    loop.close()
