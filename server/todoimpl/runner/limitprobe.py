"""Keeps the stored plan limit honest: asks the plan for its real usage and lifts a limit it no longer backs.

An early reset (Anthropic does that) leaves `limit-until` pointing days ahead; nothing else would notice. The
probe is a free read-only call (`usage/oauth.py`), so it runs every few minutes, and the board pokes it
(`refresh_if_due`) while a limit holds runs back. The queue wakes by itself within `IDLE_WAIT`.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from todoimpl.credits import marks
from todoimpl.usage import oauth

from . import limits

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger("todoimpl.runner")
INTERVAL = 300.0
MIN_GAP = 60.0


def _plan_usage(now: float) -> oauth.Probe | None:
    """Ask the plan; looked up at call time so a test can swap oauth.fetch."""
    return oauth.fetch(now)


class LimitProbe:
    """`tick()` probes once and reconciles `limit-until`; `start()` repeats it every `interval` seconds."""

    def __init__(
        self,
        root: Path,
        *,
        fetch: Callable[[float], oauth.Probe | None] | None = None,
        clock: Callable[[], float] = time.time,
        interval: float = INTERVAL,
        min_gap: float = MIN_GAP,
    ) -> None:
        """Nothing runs until tick(), refresh_if_due() or start()."""
        self.root, self._clock = root, clock
        self._fetch = fetch or _plan_usage
        self._interval, self._min_gap = interval, min_gap
        self._last = float("-inf")
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._once: threading.Thread | None = None
        self._lock = threading.Lock()

    def tick(self) -> oauth.Probe | None:
        """Probe once: a usable plan clears the stored limit and the exhausted mark."""
        with self._lock:
            now = self._clock()
            self._last = now
            probe = self._fetch(now)
            if probe is None:
                return None
            oauth.save(self.root, probe)
            if limits.active_until(self.root, now) is not None:
                blocked = probe.blocked_until(now)
                if blocked is None:
                    limits.clear(self.root)
                    marks.clear_exhausted(self.root)
                else:
                    limits.write_until(self.root, blocked)
            return probe

    def refresh_if_due(self) -> None:
        """Probe in the background when a limit holds and the last probe is older than `min_gap`."""
        now = self._clock()
        if limits.active_until(self.root, now) is None or now - self._last < self._min_gap:
            return
        self._last = now  # claim the slot first, so a burst of page loads probes once
        self._once = threading.Thread(target=self._safe_tick, name="limit-probe-once", daemon=True)
        self._once.start()

    def join(self) -> None:
        """Wait for a background probe started by refresh_if_due."""
        if self._once is not None:
            self._once.join(10)

    def _safe_tick(self) -> None:
        try:
            self.tick()
        except Exception:
            log.exception("limit probe crashed")

    def start(self) -> None:
        """Run the loop in a daemon thread (idempotent); the first probe happens off the startup path."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="limit-probe", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the loop and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._safe_tick()
            self._stop.wait(self._interval)
