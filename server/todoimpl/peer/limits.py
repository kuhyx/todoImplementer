"""The peer caps (kuhy, 2026-11-21) and the refusal every broken one raises, with its time to retry."""

from __future__ import annotations

from collections import deque

MAX_BYTES = 8 * 1024  # one message body, UTF-8
MAX_PENDING = 5  # undelivered messages per recipient
PER_SENDER = 10  # sends per sender per WINDOW
GLOBAL = 60  # sends across all senders per WINDOW
WINDOW = 60.0
EXPIRE = 30 * 60.0  # an undelivered message expires
MAX_HOPS = 6  # a thread's sends; the next one is a dead end
KEEP = 50  # messages kept per card
AWAIT_DEFAULT = 600.0  # await_reply's default wait
AWAIT_SLICE = 25.0  # one long-poll request waits at most this long (the client loops)
PENDING_RETRY = 5.0  # a full queue frees up when the session reads: try again soon


class Refusal(Exception):  # noqa: N818 - the hub's one refusal, not an error of the hub itself
    """A send, reply or wait the hub will not do: `message` says why, `retry_after` when a retry helps."""

    def __init__(self, message: str, retry_after: float | None = None, code: str = "bad_request") -> None:
        """Keep the reason, the retry time (seconds) and the HTTP error code."""
        super().__init__(message)
        self.message = message
        self.retry_after = retry_after
        self.code = code


class Window:
    """Send times per key over the last WINDOW seconds."""

    def __init__(self) -> None:
        """Start empty: the counts live in memory only (a restart forgets them)."""
        self._times: dict[str, deque[float]] = {}

    def retry_after(self, key: str, now: float, cap: int) -> float | None:
        """Seconds until `key` may send again, None when it may send now."""
        times = self._times.setdefault(key, deque())
        while times and times[0] <= now - WINDOW:
            times.popleft()
        return times[0] + WINDOW - now if len(times) >= cap else None

    def note(self, key: str, now: float) -> None:
        """Count one send of `key`."""
        self._times.setdefault(key, deque()).append(now)
