"""The request server: todoImplementer's guards on top of rtdb_relay's (DOCS-native-app-relay.md).

rtdb_relay already refuses unknown kinds (guard 1) and unsealed requests (guard 3). This adds, before a
handler runs: the schema check (2), replay and expiry (5), the write rate cap (6), the size cap (7), and the
lanes: write kinds one at a time, read kinds up to four at once. The opened request is put in CURRENT for the
handlers that need more than the body (the asking device).
"""

from __future__ import annotations

import asyncio
import contextvars
import json
import time
from collections import OrderedDict, deque
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay.server import RequestServer, failure

from todoimpl.http import newtask

from . import envelope, kinds

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from rtdb_relay.lease import Lease
    from rtdb_relay.rtdb import Rtdb
    from rtdb_relay.server import Handler

CURRENT: Final[contextvars.ContextVar[dict[str, Any]]] = contextvars.ContextVar("relay_request")
MAX_REQ: Final = 256 * 1024
MAX_AGE_MS: Final = 24 * 3600 * 1000
WRITES_PER_MIN: Final = 30
READ_LANES: Final = 4
DONE_KEPT: Final = 1024


class RelayServer(RequestServer):
    """RequestServer plus the board's guards and lanes; `lanes` reports what runs (worker presence)."""

    def __init__(
        self,
        rtdb: Rtdb,
        worker: str,
        handlers: Mapping[str, Handler],
        now: Callable[[], float] = time.time,
    ) -> None:
        """Serve `handlers` (keyed by the allowlist) as `worker`."""
        super().__init__(rtdb, worker, handlers, now)
        self._clock = now
        self._act = asyncio.Lock()
        self._read = asyncio.Semaphore(READ_LANES)
        self._writes: deque[float] = deque()
        self._done: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self.act: str | None = None
        self.reads = 0

    def refuse(self, kind: str, req: dict[str, Any]) -> dict[str, Any] | None:
        """Return the failed result for a request a guard stops, or None to run it."""
        cap = newtask.MAX_BODY if kind in newtask.BIG_KINDS else MAX_REQ  # inline images (T2322)
        if len(json.dumps(req, separators=(",", ":"))) > cap:
            return failure(kind, "bad_request", f"request over {cap // 1024} KB")
        if (why := envelope.problem(req)) is not None:
            return failure(kind, "bad_request", why)
        now = self._clock()
        if now * 1000 - req["sent_at"] > MAX_AGE_MS:
            return failure(kind, "expired", "request is older than 24 h")
        if kinds.lane_of(kind) == "act":
            while self._writes and self._writes[0] <= now - 60:
                self._writes.popleft()
            if len(self._writes) >= WRITES_PER_MIN:
                return failure(kind, "rate_limited", "over 30 write requests in a minute", retry=True)
            self._writes.append(now)
        return None

    async def _run(self, lease: Lease, kind: str, req: dict[str, Any]) -> dict[str, Any]:
        if (seen := self._done.get(lease.rid)) is not None:  # guard 5: a replayed rid gets its old answer
            return seen
        req = envelope.normalized(req)
        if (refused := self.refuse(kind, req)) is not None:
            return self._remember(lease.rid, refused)
        token = CURRENT.set(req)
        try:
            if kinds.lane_of(kind) == "act":
                async with self._act:
                    self.act = lease.rid
                    try:
                        result = await super()._run(lease, kind, req)
                    finally:
                        self.act = None
            else:
                async with self._read:
                    self.reads += 1
                    try:
                        result = await super()._run(lease, kind, req)
                    finally:
                        self.reads -= 1
        finally:
            CURRENT.reset(token)
        return self._remember(lease.rid, result)

    def _remember(self, rid: str, result: dict[str, Any]) -> dict[str, Any]:
        self._done[rid] = result
        while len(self._done) > DONE_KEPT:
            self._done.popitem(last=False)
        return result
