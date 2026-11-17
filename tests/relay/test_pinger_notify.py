"""notify_test (one ping to the asking device), odd presence nodes, and which cause the board banner shows."""

import asyncio
from pathlib import Path

import pytest
from pingfakes import ASKING, PHONE, FakeSender, board, notify_test, with_clients
from relayfakes import ROOT
from rtdb_relay.server import RequestError
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.credits import marks
from todoimpl.relay.fcm import BadKeyError, FcmError, UnregisteredError
from todoimpl.relay.pinger import Pinger
from todoimpl.relay.status import NOTIFY, STATUS


def test_notify_test_pings_only_the_asking_device(fake: FakeRtdb) -> None:
    with_clients(fake)
    out = FakeSender()
    assert notify_test(fake, out, "p1", board(ASKING)) == {}
    assert out.sent == [
        (PHONE, {"v": "1", "needs_you": "1", "ready": "0", "failed": "0", "at": "0000000001000"})
    ]


@pytest.mark.parametrize(
    ("dev", "error", "code"),
    [
        ("p2", None, "not_found"),  # notifications off on that device
        ("nobody", None, "not_found"),
        ("../snap", None, "not_found"),  # never a path outside presence/clients
        ("p1", UnregisteredError("FCM said 404"), "not_found"),
        ("p1", BadKeyError("no Firebase service-account key at x"), "disabled"),
    ],
)
def test_notify_test_refusals(fake: FakeRtdb, dev: str, error: Exception | None, code: str) -> None:
    with_clients(fake)
    with pytest.raises(RequestError) as caught:
        notify_test(fake, FakeSender(error), dev)
    assert caught.value.code == code


def test_notify_test_send_failure_may_be_retried(fake: FakeRtdb) -> None:
    with_clients(fake)
    with pytest.raises(RequestError) as caught:
        notify_test(fake, FakeSender(FcmError("FCM said 503")), "p1")
    assert (caught.value.code, caught.value.retry) == ("upstream_unavailable", True)
    assert NOTIFY.cause == "FCM said 503"


def test_no_presence_node_pings_nobody(fake: FakeRtdb) -> None:
    fake.set(f"{ROOT}/presence/clients", None)
    out = FakeSender()

    async def go() -> None:
        db = fake.rtdb()
        pings = Pinger(db, out)
        await pings.idle()  # nothing scheduled: returns at once
        await pings.broadcast()
        await db.aclose()

    asyncio.run(go())
    assert out.sent == []


def test_relay_cause_wins_over_the_notification_cause(tmp_path: Path) -> None:
    NOTIFY.fail("no key")
    STATUS.fail("no session")
    assert marks.active_alert(tmp_path, 0.0)["text"] == "Phone relay is off: no session"  # type: ignore[index]
    STATUS.ok()
    assert marks.active_alert(tmp_path, 0.0)["text"] == "Phone notifications are off: no key"  # type: ignore[index]
