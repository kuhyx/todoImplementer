"""The server's peer wiring: which cards take messages now, and the pump that delivers them.

A card takes peer messages while its drive runs (`Scheduler.running`) and it is no closing run; while it
ships (a landing step) messages are held and go in once it is done. The pump ticks the hub every TICK s.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.board.parse import StateError
from todoimpl.board.state import load, run_dir

from . import token
from .hub import Hub
from .pipe import RunPipe

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = logging.getLogger("todoimpl.peer")
TICK = 0.5  # seconds between pump rounds: a message reaches the turn within its next tool call plus this
LANDING = frozenset({"shipping"})


class Running(Protocol):  # noqa: D101 - the slice of the Scheduler used here
    def running(self) -> set[str]: ...  # noqa: D102


def liveness(root: Path, running: Callable[[], set[str]]) -> Callable[[str], str | None]:
    """`live(card)`: "live", "held" (landing), or None (no live session)."""

    def live(card: str) -> str | None:
        if card not in running():
            return None
        try:
            state = load(run_dir(root, card))
        except StateError:
            return None
        if state is None or state.closing:
            return None
        return "held" if state.stage in LANDING else "live"

    return live


def pump(tick: Callable[[], None], stop: threading.Event, every: float) -> None:
    """Tick until `stop`; a failing round is logged and the next one runs."""
    while not stop.is_set():
        try:
            tick()
        except Exception:
            log.exception("peer tick failed")
        stop.wait(every)


def start(root: Path, scheduler: Running) -> Hub:
    """Build the hub (creating the token file) and start its pump thread."""
    bus: Any = getattr(scheduler, "bus", None)
    publish: Callable[[str, dict[str, Any]], None] = bus.publish if bus is not None else (lambda _c, _e: None)
    hub = Hub(
        root, token.ensure(root), clock=time.time, live=liveness(root, scheduler.running), pipe=RunPipe(root),
        publish=publish,
    )  # fmt: skip
    threading.Thread(target=lambda: pump(hub.tick, threading.Event(), TICK), daemon=True).start()
    return hub
