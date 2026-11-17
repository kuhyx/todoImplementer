"""Why the relay is not serving, for the board's red banner (guard 8: a fail-closed relay is never silent).

The worker sets a cause when it cannot start (no Firebase session, no or wrong crdt-sync password, RTDB down)
and clears it once it serves. The board shows the cause as `alert` {kind: "relay"} while it is set.
"""

from __future__ import annotations

import threading
from typing import Any, Final

ALERT_S: Final = 3600.0  # the banner's `until`; it moves forward on every board read while the cause holds


class Status:
    """Thread-safe: the worker thread writes it, the HTTP threads read it."""

    def __init__(self) -> None:
        """Healthy until told otherwise (an off relay has no cause)."""
        self._lock = threading.Lock()
        self._cause: str | None = None

    @property
    def cause(self) -> str | None:
        """Return the current reason, or None."""
        with self._lock:
            return self._cause

    def fail(self, cause: str) -> None:
        """Record that the relay stopped serving because of `cause`."""
        with self._lock:
            self._cause = cause

    def ok(self) -> None:
        """Record that the relay serves."""
        with self._lock:
            self._cause = None

    def alert(self, now: float) -> dict[str, Any] | None:
        """Return the board's `alert` object while there is a cause."""
        cause = self.cause
        if cause is None:
            return None
        return {"kind": "relay", "text": f"Phone relay is off: {cause}", "until": int(now + ALERT_S)}


STATUS: Final = Status()
