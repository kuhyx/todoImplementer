"""At night the relay serves the phone nothing and holds its pings for the morning (DOCS-phone.md)."""

import asyncio

import pytest
from pingfakes import ASKING, FakeSender, board, card, with_clients
from relayfakes import answer, board_handlers, req
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl import night
from todoimpl.http.routes import Router
from todoimpl.relay import pinger
from todoimpl.relay.pinger import Pinger


def test_every_kind_is_refused_at_night(
    fake: FakeRtdb, router: Router, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_NIGHT", "00:00-23:59")
    results = answer(fake, board_handlers(router), [req("snapshot_refresh", {}), req("notify_test", {})])
    assert [(r["ok"], r["code"]) for r in results] == [(False, "disabled"), (False, "disabled")]


def test_by_day_a_kind_is_served(fake: FakeRtdb, router: Router) -> None:
    [result] = answer(fake, board_handlers(router), [req("snapshot_refresh", {})])
    assert result["ok"] is True


def test_a_night_ping_waits_for_the_morning(fake: FakeRtdb, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pinger, "COALESCE_S", 0.0)
    slept: list[float] = []
    real_sleep = asyncio.sleep

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", sleep)
    monkeypatch.setattr(night, "to_morning", lambda *_a: 3600.0)
    with_clients(fake)
    out = FakeSender()

    async def go() -> None:
        db = fake.rtdb()
        pings = Pinger(db, out)
        await pings.on_board(board(card("a")), board(ASKING))
        await pings.idle()
        await db.aclose()

    asyncio.run(go())
    assert 3600.0 in slept
    assert len(out.sent) == 2  # sent once the night is over, to both clients
