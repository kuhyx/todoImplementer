"""live_watch: mirror one card's /api/live feed to live/{card} while some client watches it.

A watch lasts WATCH_S after its last renewal (the app renews every 60 s while the drawer is open and sends
card null on close). The feed is the Router's own SSE source, so the relay sees exactly what the page sees.
Events land at live/{card}/s<9-digit n>; only the newest KEEP are kept.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Final

from todoimpl.http.routes import SseReply

from . import bridge

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from rtdb_relay.rtdb import Rtdb

    from todoimpl.http.routes import Router

log = logging.getLogger("todoimpl.relay")
WATCH_S: Final = 120.0
KEEP: Final = 200
POLL_S: Final = 5.0  # how often a quiet mirror checks whether anyone still watches


class Live:
    """The watches by device and one mirror task per watched card."""

    def __init__(self, rtdb: Rtdb, router: Router, now: Callable[[], float] = time.time) -> None:
        """Mirror through `rtdb`; feeds come from `router`."""
        self._rtdb, self._router, self._now = rtdb, router, now
        self.watches: dict[str, tuple[str, float]] = {}
        self.mirrors: dict[str, asyncio.Task[None]] = {}
        self.poll = POLL_S

    def watched(self, card: str) -> bool:
        """Tell whether some device's watch on `card` has not lapsed."""
        now = self._now()
        return any(c == card and until > now for c, until in self.watches.values())

    async def watch(self, dev: str, card: str | None) -> dict[str, Any]:
        """Start, renew or (card None) end `dev`'s watch; the feed starts in the background."""
        if card is None:
            self.watches.pop(dev, None)
            await self._rtdb.delete(f"watch/{dev}")
            return {}
        stream: SseReply | None = None
        if card not in self.mirrors:  # a running mirror already proved the card streams
            reply = await asyncio.to_thread(self._router.get, f"/api/live?id={card}")
            if not isinstance(reply, SseReply):
                raise bridge.refusal(reply)  # the route's refusal: unknown card, bad id
            stream = reply
        until = self._now() + WATCH_S
        self.watches[dev] = (card, until)
        await self._rtdb.put(f"watch/{dev}", {"card": card, "until": int(until * 1000)})
        if stream is not None:
            self.mirrors[card] = asyncio.create_task(self._mirror(card, stream))
        return {}

    async def _mirror(self, card: str, reply: SseReply) -> None:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop = threading.Event()
        threading.Thread(target=_pump, args=(reply.events, queue, loop, stop), daemon=True).start()
        n = 0
        try:
            item: dict[str, Any] | None = reply.snapshot
            while self.watched(card):
                if item is not None:
                    n += 1
                    await self._rtdb.put(f"live/{card}/s{n:09d}", item)
                    if n > KEEP:
                        await self._rtdb.delete(f"live/{card}/s{n - KEEP:09d}")
                try:
                    item = await asyncio.wait_for(queue.get(), self.poll)
                except TimeoutError:
                    item = None
                    continue
                if item is None:
                    break
        except Exception:
            log.exception("relay: live mirror of %s failed", card)
        finally:
            stop.set()
            self.mirrors.pop(card, None)


def _pump(
    events: Iterator[dict[str, Any]],
    queue: asyncio.Queue[dict[str, Any] | None],
    loop: asyncio.AbstractEventLoop,
    stop: threading.Event,
) -> None:
    """Move the blocking feed into the loop's queue; None marks its end."""
    with contextlib.suppress(RuntimeError):  # the loop closed under us: nobody is listening
        for event in events:
            if stop.is_set():
                break
            loop.call_soon_threadsafe(queue.put_nowait, event)
        loop.call_soon_threadsafe(queue.put_nowait, None)
