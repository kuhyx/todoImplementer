"""The phone feed of a reopened repo card drops the earlier cycle's lines in every order of events (T2484).

T2479 dropped them only when a mirror started with all its stored lines at or below the cycle floor. A mirror
that ran across the reopen wrote the new cycle's first lines, so no later mirror dropped the old ones.
"""

import asyncio
import time
from collections.abc import Iterator
from typing import Any

from httpfakes import FakeBackend
from relayfakes import ROOT
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from test_live_resume import activities, activity, open_once
from todoimpl.http.routes import Router
from todoimpl.relay.live import Live


def test_t2484_a_mirror_running_across_the_reopen_drops_the_old_cycle(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    card = backend.task_id

    def feed() -> Iterator[dict[str, Any]]:
        yield from (activity(n) for n in range(1, 31))
        time.sleep(0.3)  # the old cycle's lines land in their own write first
        backend.floor_seq = 40  # Start records the new cycle's floor
        yield {"type": "stage", "stage": "plan"}
        yield from (activity(41), activity(42))

    async def go() -> None:
        db = fake.rtdb()
        lv = Live(db, router)
        lv.gather = 0.05
        backend.events = feed()  # type: ignore[assignment]
        await open_once(db, lv, card)
        await db.aclose()

    asyncio.run(go())
    assert activities(fake.get(f"{ROOT}/live/{card}")) == [41, 42]


def test_t2484_a_restart_drops_old_lines_below_the_new_cycles_first_lines(
    fake: FakeRtdb, router: Router, backend: FakeBackend
) -> None:
    card = backend.task_id

    async def go() -> None:
        db = fake.rtdb()
        backend.events = [activity(n) for n in range(1, 31)]
        await open_once(db, Live(db, router), card)
        backend.events = [activity(41), activity(42)]  # mirrored before the floor was known
        await open_once(db, Live(db, router), card)
        backend.floor_seq, backend.events = 40, [activity(41), activity(42), activity(43)]
        await open_once(db, Live(db, router), card)  # a server restart: nothing in memory
        await db.aclose()

    asyncio.run(go())
    feed = fake.get(f"{ROOT}/live/{card}")
    assert activities(feed) == [41, 42, 43]
    assert all(v.get("seq", 41) > 40 for v in feed.values())
