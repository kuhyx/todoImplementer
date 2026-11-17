"""The worker heartbeat at presence/workers/{worker}; it replaces GET /version.

`beat` is an RTDB server timestamp kept clear beside the sealed unit. `skew_ms` is how far the server clock
was from this PC's when the previous beat was written, so a client can read the lease times in server time.
"""

from __future__ import annotations

import asyncio
import os
import socket
import time
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay.rtdb import SERVER_TIME

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from rtdb_relay.rtdb import Rtdb

BEAT_S: Final = 30.0


class Heart:
    """Writes one beat now and then; `lanes` reports what the request server is running."""

    def __init__(
        self,
        rtdb: Rtdb,
        worker: str,
        lanes: Callable[[], dict[str, Any]],
        *,
        release: tuple[str, str],
        now: Callable[[], float] = time.time,
    ) -> None:
        """Beat as `worker`, naming the live server's (version, build)."""
        self._rtdb, self._worker, self._lanes, self._now = rtdb, worker, lanes, now
        self._base = {
            "host": socket.gethostname(),
            "pid": os.getpid(),
            "version": release[0],
            "build": release[1],
            "started": int(now() * 1000),
        }
        self.skew_ms = 0

    async def beat(self) -> None:
        """Write one beat and learn the clock skew from the timestamp the server put in it."""
        sent = int(self._now() * 1000)
        node = {**self._base, "beat": SERVER_TIME, "lanes": self._lanes(), "skew_ms": self.skew_ms}
        written = await self._rtdb.put(f"presence/workers/{self._worker}", node)
        beat = written.get("beat") if isinstance(written, dict) else None
        if isinstance(beat, int) and not isinstance(beat, bool):
            self.skew_ms = beat - sent

    async def run(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        """Beat every BEAT_S until cancelled."""
        while True:
            await self.beat()
            await sleep(BEAT_S)
