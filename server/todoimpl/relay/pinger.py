"""FCM pings on board changes (DOCS-native-app-relay.md "Notifications").

After each board publish the worker compares the old and the new board: a card that newly sits in Needs you
(category other than `auto`), or newly has a failed run or failed checks, raises one ping. A card that is
ready ships by itself (T2060), so it earns none. Changes inside COALESCE_S share one ping. The ping goes to
every presence/clients/* entry with an `fcm` token and holds counts only (relay-nodes.schema.json ping).
Failures land on the board banner (NOTIFY).
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Final, Protocol

from rtdb_relay.server import RequestError

from .fcm import BadKeyError, FcmError, UnregisteredError
from .server import CURRENT
from .status import NOTIFY

if TYPE_CHECKING:
    from collections.abc import Callable

    from rtdb_relay.rtdb import Rtdb

log = logging.getLogger("todoimpl.relay")
COALESCE_S: Final = 2.0
FAILED: Final = frozenset({"run_failed", "checks_failed"})
DEVICE: Final = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class Sender(Protocol):
    """What the pinger needs from fcm.Sender."""

    def check(self) -> object:
        """Raise BadKeyError when the key is missing or unusable."""

    async def send(self, token: str, data: dict[str, str]) -> None:
        """Send one data-only message."""


def cards(board: object) -> dict[str, dict[str, Any]]:
    """Return the board's cards by id (anything malformed is skipped)."""
    columns = board.get("columns") if isinstance(board, dict) else None
    found: dict[str, dict[str, Any]] = {}
    for column in columns if isinstance(columns, list) else []:
        items = column.get("items") if isinstance(column, dict) else None
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                found[item["id"]] = item
    return found


def marks(card: dict[str, Any]) -> set[str]:
    """Return which ping counters the card adds to."""
    raw = card.get("needs")
    needs: dict[str, Any] = raw if isinstance(raw, dict) else {}
    out: set[str] = set()
    if card.get("column") == "needs_you" and needs.get("category") != "auto":
        out.add("needs_you")
    if needs.get("kind") in FAILED:
        out.add("failed")
    return out


def fresh(old: object, new: object) -> bool:
    """Tell whether some card newly earns a counter; the first board after a start never does."""
    if old is None:
        return False
    before = cards(old)
    return any(marks(card) - marks(before.get(cid, {})) for cid, card in cards(new).items())


def ping(board: object, now_ms: int) -> dict[str, str]:
    """Return the FCM data payload: counts only, all strings (FCM data values are strings)."""
    totals = dict.fromkeys(("needs_you", "failed"), 0)
    for card in cards(board).values():
        for mark in marks(card):
            totals[mark] += 1
    return {"v": "1", **{k: str(v) for k, v in totals.items()}, "at": f"{now_ms:013d}"}


class Pinger:
    """Hooks into Publisher(on_board=...) and answers the notify_test kind."""

    def __init__(self, rtdb: Rtdb, sender: Sender, *, now: Callable[[], float] = time.time) -> None:
        """Ping through `sender` the clients registered in `rtdb`."""
        self._rtdb, self._sender, self._now = rtdb, sender, now
        self._last: dict[str, Any] | None = None
        self._pending: asyncio.Task[None] | None = None

    def check(self) -> None:
        """Load the key now, so a missing one shows on the banner before any ping is due."""
        try:
            self._sender.check()
        except BadKeyError as err:
            NOTIFY.fail(str(err))
            log.warning("relay: notifications off: %s", err)
        else:
            NOTIFY.ok()

    async def on_board(self, old: dict[str, Any] | None, new: dict[str, Any]) -> None:
        """Remember the board; schedule one ping when it holds something new."""
        self._last = new
        if fresh(old, new) and self._pending is None:
            self._pending = asyncio.create_task(self._later())

    async def idle(self) -> None:
        """Wait for a scheduled ping to go out."""
        if self._pending is not None:
            await self._pending

    async def _later(self) -> None:
        await asyncio.sleep(COALESCE_S)
        self._pending = None
        try:
            await self.broadcast()
        except Exception as exc:  # noqa: BLE001 - a background ping must never kill the publisher
            NOTIFY.fail(str(exc) or type(exc).__name__)
            log.warning("relay: ping failed: %s", exc)

    def _payload(self) -> dict[str, str]:
        return ping(self._last, int(self._now() * 1000))

    async def broadcast(self) -> None:
        """Ping every client that has a token; a refusal shows on the banner, a sent ping clears it."""
        clients = await self._rtdb.get("presence/clients")
        entries = clients.values() if isinstance(clients, dict) else []
        tokens = [c["fcm"] for c in entries if isinstance(c, dict) and isinstance(c.get("fcm"), str)]
        data, failure = self._payload(), None
        for token in tokens:
            try:
                await self._sender.send(token, data)
            except UnregisteredError as err:
                log.info("relay: a device token is gone: %s", err)
            except FcmError as err:
                failure = str(err)
        if failure is not None:
            NOTIFY.fail(failure)
        elif tokens:
            NOTIFY.ok()
        log.info("relay: pinged %d device(s)", len(tokens))

    async def notify_test(self, body: dict[str, Any]) -> dict[str, Any]:
        """Answer the notify_test kind: one ping with the current counts to the asking device only."""
        del body
        dev = str(CURRENT.get()["dev"])
        node = await self._rtdb.get(f"presence/clients/{dev}") if DEVICE.match(dev) else None
        token = node.get("fcm") if isinstance(node, dict) else None
        if not isinstance(token, str):
            raise RequestError(code="not_found", message="this device has no notification token")
        try:
            await self._sender.send(token, self._payload())
        except BadKeyError as err:
            NOTIFY.fail(str(err))
            raise RequestError(code="disabled", message=str(err)) from None
        except UnregisteredError as err:
            raise RequestError(code="not_found", message=str(err)) from None
        except FcmError as err:
            NOTIFY.fail(str(err))
            raise RequestError(code="upstream_unavailable", message=str(err), retry=True) from None
        NOTIFY.ok()
        return {}
