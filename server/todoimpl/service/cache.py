"""Background-refreshed snapshot of the todo notes, so /api/board never waits on the MCP server."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

    from .cards import CardTask

log = logging.getLogger("todoimpl.service")
INTERVAL = 4.0
NOT_LOADED = "notes not loaded yet"


@dataclass(frozen=True)
class Snapshot:
    """The last good cards plus the error of the latest refresh (None when it succeeded)."""

    tasks: tuple[CardTask, ...] = ()
    error: str | None = NOT_LOADED
    at: float = 0.0
    loaded: bool = False  # True once any fetch succeeded: the cards may be stale, but they were real


class TaskCache:
    """Holds a Snapshot; refresh() runs fetch, a daemon thread repeats it `interval` s after each finish."""

    def __init__(
        self,
        fetch: Callable[[], list[CardTask]],
        interval: float = INTERVAL,
        clock: Callable[[], float] = time.time,
    ) -> None:
        """Nothing is fetched until refresh() or start()."""
        self._fetch = fetch
        self._interval = interval
        self._clock = clock
        self._snap = Snapshot()
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> Snapshot:
        """Return the current snapshot without touching the network."""
        with self._lock:
            return self._snap

    def refresh(self) -> Snapshot:
        """Fetch now; a failure keeps the old cards but records why, it never reads as an empty board."""
        try:
            fresh = Snapshot(tuple(self._fetch()), None, self._clock(), loaded=True)
        except Exception as exc:  # noqa: BLE001 - the loop must survive anything; the message reaches the page
            log.warning("todo refresh failed: %s", exc)
            with self._lock:
                fresh = replace(self._snap, error=f"{type(exc).__name__}: {exc}", at=self._clock())
        with self._lock:
            self._snap = fresh
        return fresh

    def poke(self) -> None:
        """Refresh as soon as possible (after an action changed a note)."""
        self._wake.set()

    def start(self) -> None:
        """Start the refresh thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="todo-cache", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._interval)
            self._wake.clear()
            if not self._stop.is_set():
                self.refresh()
