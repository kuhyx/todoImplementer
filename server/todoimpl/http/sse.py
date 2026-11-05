"""Server-sent events: framing, replay filter and a 15 s keepalive over a blocking event source."""

from __future__ import annotations

import json
import logging
import queue
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

log = logging.getLogger("todoimpl.http")
KEEPALIVE = b": keepalive\n\n"
_END = object()


def frame(event: dict[str, Any]) -> bytes:
    """Encode one event as an SSE message; events with a seq carry it as the message id."""
    head = f"id: {event['seq']}\n" if "seq" in event else ""
    data = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
    return f"{head}event: {event['type']}\ndata: {data}\n\n".encode()


def _pump(events: Iterator[dict[str, Any]], out: queue.Queue[Any], stop: threading.Event) -> None:
    """Move events into the queue so the writer can wake for keepalives; closes the source when asked."""
    try:
        for event in events:
            if stop.is_set():
                break
            out.put(event)
    except Exception:
        log.exception("live source failed")
    finally:
        close = getattr(events, "close", None)
        if close is not None:
            close()
        out.put(_END)


def stream(
    write: Callable[[bytes], None],
    snapshot: dict[str, Any],
    events: Iterator[dict[str, Any]],
    last_seq: int,
    heartbeat: float,
) -> None:
    """Write the snapshot, then every event newer than last_seq, a keepalive per idle heartbeat.

    A dead client makes write raise (BrokenPipeError and friends); that propagates after the source is
    told to stop. A source stuck between events is only released at its next event.
    """
    out: queue.Queue[Any] = queue.Queue()
    stop = threading.Event()
    threading.Thread(target=_pump, args=(events, out, stop), daemon=True).start()
    try:
        write(frame(snapshot))
        while True:
            try:
                item = out.get(timeout=heartbeat)
            except queue.Empty:
                write(KEEPALIVE)
                continue
            if item is _END:
                return
            if item["type"] == "activity" and item.get("seq", 0) <= last_seq:
                continue
            write(frame(item))
    finally:
        stop.set()
