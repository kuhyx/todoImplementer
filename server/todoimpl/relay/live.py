"""live_watch: mirror one card's /api/live feed to live/{card} while some client watches it.

A watch lasts WATCH_S after its last renewal (the app renews every 60 s while the drawer is open and sends
card null on close). The feed is the Router's own SSE source, so the relay sees exactly what the page sees.
Events land at live/{card}/s<9-digit n>; only the newest KEEP are kept. A new mirror (server restart, lapsed
watch) continues above the highest stored key, so new events never sort below old ones (T2312), and skips
the activity the feed already holds: the source replays events.jsonl from the start on every open (T2345).
Events land in one PATCH per GATHER_S, the trim riding along (T2346).
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
import threading
import time
from collections import deque
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
GATHER_S: Final = 1.0  # events are written (and reach the phone) at most once a second, in one PATCH
FLOOR_READS: Final = 5  # newest keys read back for the last mirrored seq (a stage or done event has none)
_KEY: Final = re.compile(r"s(\d{9})")


class Live:
    """The watches by device and one mirror task per watched card."""

    def __init__(self, rtdb: Rtdb, router: Router, now: Callable[[], float] = time.time) -> None:
        """Mirror through `rtdb`; feeds come from `router`."""
        self._rtdb, self._router, self._now = rtdb, router, now
        self.watches: dict[str, tuple[str, float]] = {}
        self.mirrors: dict[str, asyncio.Task[None]] = {}
        self.floors: dict[str, int] = {}  # newest activity seq mirrored per card
        self.poll = POLL_S
        self.gather = GATHER_S

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

    async def _stored(self, card: str) -> deque[int]:
        """Return the seq numbers already under live/{card}, ascending (a shallow read: keys only)."""
        node = await self._rtdb.get(f"live/{card}", {"shallow": "true"})
        keys = node if isinstance(node, dict) else {}
        return deque(sorted(int(m[1]) for k in keys if (m := _KEY.fullmatch(k))))

    async def _floor(self, card: str, kept: deque[int]) -> int:
        """Return the newest activity seq mirrored: the in-memory one, else read back from the newest keys."""
        if card in self.floors:
            return self.floors[card]
        for n in list(kept)[-1 : -FLOOR_READS - 1 : -1]:
            item = await self._rtdb.get(f"live/{card}/s{n:09d}")
            if isinstance(item, dict) and isinstance(seq := item.get("seq"), int):
                return seq
        return 0

    def _fresh(self, card: str, batch: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Drop activity the feed already holds (a reopen replays events.jsonl from the start, T2345)."""
        floor = self.floors.get(card, 0)
        out = []
        for item in batch:
            seq = item.get("seq") if item.get("type") == "activity" else None
            if isinstance(seq, int):
                if seq <= floor:
                    continue
                floor = seq
            out.append(item)
        self.floors[card] = floor
        return out[-KEEP:]

    async def _write(self, card: str, items: list[dict[str, Any]], kept: deque[int]) -> None:
        """Land `items` and trim to KEEP in one PATCH (T2346: a burst cost one PUT per event)."""
        n = kept[-1] if kept else 0
        change: dict[str, Any] = {}
        for item in items:
            n += 1
            change[f"s{n:09d}"] = item
            kept.append(n)
        while len(kept) > KEEP:
            gone = f"s{kept.popleft():09d}"
            if change.pop(gone, None) is None:
                change[gone] = None
        await self._rtdb.patch(f"live/{card}", change)

    async def _mirror(self, card: str, reply: SseReply) -> None:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()
        loop = asyncio.get_running_loop()
        stop = threading.Event()
        threading.Thread(target=_pump, args=(reply.events, queue, loop, stop), daemon=True).start()
        try:
            kept = await self._stored(card)
            self.floors[card] = await self._floor(card, kept)
            batch, ended = [reply.snapshot], False
            while self.watched(card):
                if items := self._fresh(card, batch):
                    await self._write(card, items, kept)
                if ended:
                    break
                batch, ended = await _drain(queue, self.poll, self.gather)
        except Exception:
            log.exception("relay: live mirror of %s failed", card)
        finally:
            stop.set()
            self.mirrors.pop(card, None)


async def _drain(
    queue: asyncio.Queue[dict[str, Any] | None], wait: float, gather: float
) -> tuple[list[dict[str, Any]], bool]:
    """Wait up to `wait` for an event, then collect for `gather` seconds; True once the feed ended."""
    try:
        item = await asyncio.wait_for(queue.get(), wait)
    except TimeoutError:
        return [], False
    batch: list[dict[str, Any]] = []
    deadline = asyncio.get_running_loop().time() + gather
    while item is not None:
        batch.append(item)
        try:
            item = await asyncio.wait_for(queue.get(), max(0.0, deadline - asyncio.get_running_loop().time()))
        except TimeoutError:
            return batch, False
    return batch, True


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
