"""Sealed snapshot nodes: snap/{board,usage,sessions,merges}, each exactly its GET body, then rev bumped.

The worker reads each node from the Router on its own interval and writes it only when the JSON changed. A
client streams the clear `rev` counters and GETs a snap node when its counter moves. After a board write the
`on_board` seam sees the old and the new board (the FCM pinger hooks in there, DOCS-native-app-relay.md
"Notifications").
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Final

from .layout import META, NODES

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

    from rtdb_relay.rtdb import Rtdb

    type Source = Callable[[], dict[str, Any]]
    type OnBoard = Callable[[dict[str, Any] | None, dict[str, Any]], Awaitable[None]]

log = logging.getLogger("todoimpl.relay")
INTERVALS: Final = {"board": 1.0, "usage": 10.0, "sessions": 5.0, "merges": 10.0}
TICK: Final = 0.25  # no node is written more often than this


class Publisher:
    """Keeps the snap nodes equal to what the Router answers."""

    def __init__(
        self,
        rtdb: Rtdb,
        sources: Mapping[str, Source],
        *,
        on_board: OnBoard | None = None,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Publish the nodes of `sources` (a subset of NODES) through `rtdb`."""
        self._rtdb, self._sources, self._on_board = rtdb, sources, on_board
        self._sleep, self._clock = sleep, clock
        self._text: dict[str, str] = {}
        self._board: dict[str, Any] | None = None
        self.rev = dict.fromkeys(NODES, 0)
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        """Write meta and carry on from the counters already in the tree (a restart never moves rev back)."""
        current = await self._rtdb.get("rev")
        if isinstance(current, dict):
            for name in NODES:
                value = current.get(name)
                if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                    self.rev[name] = value
        await self._rtdb.put("meta", META)

    async def publish(self, name: str, *, force: bool = False) -> bool:
        """Write snap/<name> when it changed (always when `force`); True when it was written."""
        try:
            value = await asyncio.to_thread(self._sources[name])
        except Exception as exc:  # noqa: BLE001 - one failing source must not stop the others
            log.warning("relay: cannot read %s: %s", name, exc)
            return False
        text = json.dumps(value, sort_keys=True, separators=(",", ":"))
        async with self._lock:
            if not force and self._text.get(name) == text:
                return False
            await self._rtdb.put(f"snap/{name}", value)
            self.rev[name] += 1
            await self._rtdb.patch("rev", {name: self.rev[name]})
            self._text[name] = text
        if name == "board":
            previous, self._board = self._board, value
            if self._on_board is not None:
                await self._on_board(previous, value)
        return True

    async def refresh_all(self) -> None:
        """Republish every node (the `snapshot_refresh` kind: pull to refresh, first start)."""
        for name in self._sources:
            await self.publish(name, force=True)

    async def run(self) -> None:
        """Poll each node on its interval until cancelled."""
        due = dict.fromkeys(self._sources, 0.0)
        while True:
            now = self._clock()
            for name, at in due.items():
                if at <= now:
                    await self.publish(name)
                    due[name] = now + INTERVALS.get(name, 1.0)
            await self._sleep(TICK)
