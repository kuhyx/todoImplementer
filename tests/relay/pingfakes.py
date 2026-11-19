"""Boards, clients and a fake FCM sender for the pinger tests."""

import asyncio
from typing import Any

from relayfakes import ROOT
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.relay.fcm import BadKeyError
from todoimpl.relay.pinger import Pinger
from todoimpl.relay.server import CURRENT

PHONE = "token-phone-1-aaaaaaaaaaaa"
WEB = "token-web-1-bbbbbbbbbbbbbbb"


def card(cid: str, column: str = "backlog", status: str = "backlog", needs: Any = None) -> dict[str, Any]:
    return {"id": cid, "column": column, "status": status, "needs": needs}


def needs(kind: str = "claude_question", category: str = "questions") -> dict[str, Any]:
    return {"kind": kind, "text": "t", "category": category, "effort": 1}


def board(*cards: dict[str, Any]) -> dict[str, Any]:
    columns = ("backlog", "running", "needs_you", "done")
    return {"columns": [{"id": c, "items": [x for x in cards if x["column"] == c]} for c in columns]}


ASKING = card("a", "needs_you", "needs_you", needs())
AUTO = card("b", "needs_you", "needs_you", needs(category="auto"))
SHIPPING = card("c", "running", "shipping")  # a green card ships itself (T2060): it never pings
FAILED = card("d", "needs_you", "needs_you", needs("run_failed", "action"))


class FakeSender:
    """Records what it sends; `error` makes check() (key errors only) and send() fail."""

    def __init__(self, error: Exception | None = None) -> None:
        self.sent: list[tuple[str, dict[str, str]]] = []
        self.error = error

    def check(self) -> None:
        if isinstance(self.error, BadKeyError):
            raise self.error

    async def send(self, token: str, data: dict[str, str]) -> None:
        if self.error is not None:
            raise self.error
        self.sent.append((token, data))


def client(fcm_token: str | None) -> dict[str, Any]:
    return {"platform": "android", "app": "1.0.0", "build": 1, "seen": 1, "fcm": fcm_token}


def with_clients(fake: FakeRtdb) -> None:
    """Two devices with a token (p1, w1) and one with notifications off (p2)."""
    fake.set(f"{ROOT}/presence/clients/p1", client(PHONE))
    fake.set(f"{ROOT}/presence/clients/p2", client(None))
    fake.set(f"{ROOT}/presence/clients/w1", client(WEB))


def notify_test(fake: FakeRtdb, out: FakeSender, dev: str, last: Any = None) -> dict[str, Any]:
    """Answer one notify_test as device `dev`, the last published board being `last`."""

    async def go() -> dict[str, Any]:
        db = fake.rtdb()
        pings = Pinger(db, out, now=lambda: 1.0)
        if last is not None:
            await pings.on_board(None, last)
        token = CURRENT.set({"dev": dev})
        try:
            return await pings.notify_test({})
        finally:
            CURRENT.reset(token)
            await db.aclose()

    return asyncio.run(go())
