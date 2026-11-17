"""The relay worker: one thread with its own event loop beside the HTTP server (DOCS-native-app-relay.md).

Off unless TODOIMPL_RELAY=1 (the systemd unit sets it; tests never do). Fail closed (guard 8): until the
Firebase session and the crdt-sync passphrase both work, the worker writes nothing and serves nothing, the
HTTP board keeps working and its banner names the cause; it retries on its own (5 s, 15 s, then every 60 s).
"""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

import httpx
from rtdb_relay.seal import Sealer
from rtdb_relay.unlock import unlock

from todoimpl.version import __version__

from . import bridge, connect, fcm, kinds
from .layout import E2E, LAYOUT
from .live import Live
from .pinger import Pinger
from .presence import Heart
from .publisher import Publisher
from .server import CURRENT, RelayServer
from .status import STATUS

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from rtdb_relay.server import Handler

    from todoimpl.http.routes import Router

    from .pinger import Sender
    from .publisher import Source

log = logging.getLogger("todoimpl.relay")
RETRY_S: Final = (5.0, 15.0, 60.0)
SNAP_PATHS: Final = {
    "board": "/api/board",
    "usage": "/api/usage",
    "sessions": "/api/sessions",
    "merges": "/api/merges",
}


def sources(router: Router) -> dict[str, Source]:
    """Read each snap node through the Router: exactly its GET body."""

    def read(path: str) -> Source:
        return lambda: bridge.data_of(bridge.send(router, kinds.Call("GET", path)))

    return {name: read(path) for name, path in SNAP_PATHS.items()}


def handlers(router: Router, publisher: Publisher, live: Live, notify: Handler) -> dict[str, Handler]:
    """Build one handler per allowlisted kind; routed kinds go through the Router like a click."""

    def routed(kind: kinds.Kind) -> Handler:
        async def run(body: dict[str, Any]) -> dict[str, Any]:
            reply = await asyncio.to_thread(bridge.send, router, kind.call(body))
            return {"data": bridge.data_of(reply)}  # nested: a body's own ok, kind or at never collides

        return run

    async def refresh(body: dict[str, Any]) -> dict[str, Any]:
        del body
        await publisher.refresh_all()
        return {}

    async def watch(body: dict[str, Any]) -> dict[str, Any]:
        return await live.watch(str(CURRENT.get()["dev"]), body["card"])

    table: dict[str, Handler] = {name: routed(kind) for name, kind in kinds.ROUTED.items()}
    return {**table, "live_watch": watch, "snapshot_refresh": refresh, "notify_test": notify}


@dataclass(frozen=True)
class Wiring:
    """What the worker serves (Router, build, run root), where it connects and pings; tests swap the rest."""

    router: Router
    build: str
    root: Path
    endpoint: Callable[[], connect.Endpoint] = connect.connect
    secret: Callable[[], str] = connect.passphrase
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep
    sender: Callable[[httpx.AsyncClient], Sender] = fcm.Sender


async def serve(
    endpoint: connect.Endpoint, secret: str, wiring: Wiring, *, worker: str, ready: asyncio.Event
) -> None:
    """Unlock, then serve requests, publish snapshots and beat until something fails."""
    raw = endpoint.client()
    try:
        key = await unlock(raw, secret, E2E)
    finally:
        await raw.aclose()
    rtdb = endpoint.client(LAYOUT.root, Sealer(key.cipher(), LAYOUT))
    http = httpx.AsyncClient()
    try:
        pinger = Pinger(rtdb, wiring.sender(http))
        pinger.check()
        publisher = Publisher(rtdb, sources(wiring.router), on_board=pinger.on_board)
        live = Live(rtdb, wiring.router)
        server = RelayServer(rtdb, worker, handlers(wiring.router, publisher, live, pinger.notify_test))

        def lanes() -> dict[str, Any]:
            return {"act": server.act, "read": server.reads}

        heart = Heart(rtdb, worker, lanes, release=(__version__, wiring.build))
        await publisher.start()
        STATUS.ok()
        ready.set()
        log.info("relay: serving as %s", worker)
        async with asyncio.TaskGroup() as group:
            group.create_task(server.run())
            group.create_task(publisher.run())
            group.create_task(heart.run())
    finally:
        await http.aclose()
        await rtdb.aclose()


def cause_of(exc: BaseException) -> str:
    """Return the first real error inside (exception groups unwrapped), as one line for the banner."""
    while isinstance(exc, BaseExceptionGroup) and exc.exceptions:
        exc = exc.exceptions[0]
    return str(exc) or type(exc).__name__


async def run_forever(wiring: Wiring) -> None:
    """Serve, and after any failure report it and try again, until cancelled."""
    attempt = 0
    while True:
        ready = asyncio.Event()
        try:
            worker = connect.device_id(wiring.root)
            await serve(wiring.endpoint(), wiring.secret(), wiring, worker=worker, ready=ready)
        except Exception as exc:  # noqa: BLE001 - any failure is shown and retried, never fatal
            STATUS.fail(cause_of(exc))
            log.warning("relay: not serving: %s", cause_of(exc))
        attempt = 0 if ready.is_set() else attempt + 1
        await wiring.sleep(RETRY_S[min(max(attempt - 1, 0), len(RETRY_S) - 1)])


def start(router: Router, *, build: str, root: Path, env: Mapping[str, str]) -> threading.Thread | None:
    """Start the worker thread when TODOIMPL_RELAY=1; None (and nothing touched) otherwise."""
    if env.get("TODOIMPL_RELAY") != "1":
        log.info("relay: off (TODOIMPL_RELAY is not 1)")
        return None
    wiring = Wiring(router, build, root)
    thread = threading.Thread(target=lambda: asyncio.run(run_forever(wiring)), name="relay", daemon=True)
    thread.start()
    return thread
