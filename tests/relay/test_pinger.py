"""The pinger: which board changes ping, coalescing, every client with a token, failures on the banner."""

import asyncio
from typing import Any

import pytest
from pingfakes import ASKING, AUTO, FAILED, PHONE, READY, WEB, FakeSender, board, card, needs, with_clients
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.relay import pinger
from todoimpl.relay.fcm import BadKeyError, FcmError, UnregisteredError
from todoimpl.relay.pinger import Pinger
from todoimpl.relay.status import NOTIFY


@pytest.fixture(autouse=True)
def _no_wait(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(pinger, "COALESCE_S", 0.0)


@pytest.mark.parametrize(
    ("old", "new", "fires"),
    [
        (None, board(ASKING), False),  # the first publish after a start is not a change
        (board(card("a")), board(ASKING), True),
        (board(), board(ASKING), True),  # a new card straight into Needs you
        (board(ASKING), board(ASKING), False),  # still there: no second ping
        (board(card("b")), board(AUTO), False),  # the server heals auto itself
        (board(card("c", "running", "working")), board(READY), True),
        (
            board(ASKING),
            board(card("a", "needs_you", "needs_you", needs("run_failed", "action")), FAILED),
            True,
        ),
        (board(READY), board(card("c", "done", "done")), False),
        ({"columns": "odd"}, {"columns": [{"id": "x"}, 3, {"items": [7, {"id": 5}]}]}, False),
    ],
)
def test_fresh(old: Any, new: Any, fires: bool) -> None:
    assert pinger.fresh(old, new) is fires


def test_ping_holds_counts_only() -> None:
    assert pinger.ping(board(ASKING, AUTO, READY, FAILED), 1_800_000_000_123) == {
        "v": "1",
        "needs_you": "2",
        "ready": "1",
        "failed": "1",
        "at": "1800000000123",
    }


def pinged(fake: FakeRtdb, out: FakeSender, *changes: tuple[Any, Any], now: float = 1.0) -> None:
    """Publish each (old, new) board change, then wait for the ping to go out."""

    async def go() -> None:
        db = fake.rtdb()
        pings = Pinger(db, out, now=lambda: now)
        for old, new in changes:
            await pings.on_board(old, new)
        await pings.idle()
        await db.aclose()

    asyncio.run(go())


def test_changes_coalesce_into_one_ping_to_every_token(fake: FakeRtdb) -> None:
    with_clients(fake)
    out = FakeSender()
    pinged(
        fake,
        out,
        (board(card("a")), board(ASKING)),
        (board(ASKING), board(ASKING, READY)),
        (board(ASKING, READY), board(ASKING, READY)),
        now=1_800_000_000.5,
    )
    assert sorted(t for t, _ in out.sent) == [PHONE, WEB]
    assert {d["needs_you"] + d["ready"] for _, d in out.sent} == {"11"}
    assert out.sent[0][1]["at"] == "1800000000500"


def test_no_clients_sends_nothing(fake: FakeRtdb) -> None:
    out = FakeSender()
    pinged(fake, out, (board(), board(ASKING)))
    assert out.sent == []
    assert NOTIFY.cause is None


def test_a_failing_send_goes_on_the_banner_and_a_good_one_clears_it(fake: FakeRtdb) -> None:
    with_clients(fake)
    out = FakeSender(FcmError("FCM said 503"))
    pinged(fake, out, (board(), board(ASKING)))
    assert NOTIFY.cause == "FCM said 503"
    out.error = None
    pinged(fake, out, (board(), board(READY)))
    assert NOTIFY.cause is None
    assert NOTIFY.alert(0) is None


def test_an_unregistered_token_is_skipped_quietly(fake: FakeRtdb) -> None:
    with_clients(fake)
    pinged(fake, FakeSender(UnregisteredError("FCM said 404")), (board(), board(ASKING)))
    assert NOTIFY.cause is None


def test_check_puts_a_missing_key_on_the_banner() -> None:
    out = FakeSender(BadKeyError("no Firebase service-account key at x"))
    Pinger(None, out).check()  # type: ignore[arg-type]
    assert NOTIFY.alert(100) == {
        "kind": "relay",
        "text": "Phone notifications are off: no Firebase service-account key at x",
        "until": 3700,
    }
    out.error = None
    Pinger(None, out).check()  # type: ignore[arg-type]
    assert NOTIFY.cause is None


def test_a_broken_read_in_the_background_goes_on_the_banner() -> None:
    class Broken:
        async def get(self, path: str) -> object:
            raise RuntimeError

    async def go() -> None:
        pings = Pinger(Broken(), FakeSender())  # type: ignore[arg-type]
        await pings.on_board(board(), board(ASKING))
        await pings.idle()

    asyncio.run(go())
    assert NOTIFY.cause == "RuntimeError"
