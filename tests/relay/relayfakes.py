"""Requests as the app writes them, and a one-server answer loop over the fake RTDB."""

import asyncio
import time
from collections.abc import Callable
from typing import Any

from rtdb_relay.rtdb import Rtdb
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import worker
from todoimpl.relay.fcm import BadKeyError
from todoimpl.relay.layout import LAYOUT
from todoimpl.relay.live import Live
from todoimpl.relay.pinger import Pinger
from todoimpl.relay.publisher import Publisher
from todoimpl.relay.server import RelayServer
from todoimpl.sessions.commands import CommandResult

ROOT = LAYOUT.root
DEV = "2e7ce595-0a13-48e0-9bf2-cf7282a66964"
CARD = "abcd1234-0"
RIDS = [f"01J{n:023d}" for n in range(64)]  # valid ULIDs, in order


def req(kind: str, body: dict[str, Any], **over: Any) -> dict[str, Any]:
    """Build a request as the app writes it (sent now)."""
    return {"kind": kind, "dev": DEV, "created": 1, "sent_at": int(time.time() * 1000), "body": body, **over}


def answer(
    fake: FakeRtdb, handlers: Callable[[Rtdb], dict[str, Any]], requests: list[dict[str, Any]], **kw: Any
) -> list[dict[str, Any]]:
    """Write each request under its own rid and answer them in order on one server; return the results.

    `handlers(db)` builds the handler table on the server's own client; `kw` goes to RelayServer.


    """

    async def go() -> list[dict[str, Any]]:
        db = fake.rtdb()
        srv = RelayServer(db, "pc", handlers(db), **kw)
        out = []
        for rid, request in zip(RIDS, requests, strict=False):
            fake.set(f"{ROOT}/requests/{rid}/req", request)
            out.append(await serve_one(srv, fake, rid))
        await db.aclose()
        return out

    return asyncio.run(go())


async def serve_one(srv: RelayServer, fake: FakeRtdb, rid: str) -> dict[str, Any]:
    """Answer the request at rid and return the result node as stored (opened)."""
    node = await srv._raw.get(f"requests/{rid}")
    await srv.answer(rid, node if isinstance(node, dict) else {})
    result: dict[str, Any] = fake.get(f"{ROOT}/requests/{rid}/result")
    return result


class NoKeySender:
    """An FCM sender without a key: notify_test answers disabled."""

    def check(self) -> None:
        raise BadKeyError("no Firebase service-account key at test")

    async def send(self, token: str, data: dict[str, str]) -> None:
        self.check()


def board_handlers(router: Router) -> Callable[[Rtdb], dict[str, Any]]:
    """Build the real handler table (worker.handlers) on the server's client."""
    return lambda db: worker.handlers(
        router, Publisher(db, worker.sources(router)), Live(db, router), Pinger(db, NoKeySender()).notify_test
    )


class Recorder:
    """Ask and merge services that record each click (the routes need both on the backend)."""

    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []

    def answer(self, id8: str, ask_id: str, option: str) -> None:
        self.calls.append(("answer", id8, ask_id, option))

    def take_recommended(self, id8: str) -> None:
        self.calls.append(("take_recommended", id8))

    def run_command(self, id8: str, ask_id: str, *, add: bool) -> dict[str, Any]:
        self.calls.append(("run", id8, ask_id, add))
        return {"exit": 0}

    def undo(self, id8: str, ask_id: str) -> None:
        self.calls.append(("undo", id8, ask_id))

    def verdict(self, id8: str, ask_id: str, *, approve: bool) -> None:
        self.calls.append(("verdict", id8, ask_id, approve))

    def suggestions(self) -> dict[str, Any]:
        return {"groups": []}

    def merge(self, group_id: str) -> dict[str, Any]:
        self.calls.append(("merge", group_id))
        return {"ok": True, "merged": group_id}

    def dismiss(self, group_id: str) -> dict[str, Any]:
        self.calls.append(("dismiss", group_id))
        return {"ok": True, "dismissed": group_id}


class SessionRunner:
    """Stands in for the sessions page's subprocess runner: records argv, answers success."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout: float = 10.0) -> CommandResult:
        self.calls.append(argv)
        return CommandResult(argv=argv, returncode=0, stdout="", stderr="")
