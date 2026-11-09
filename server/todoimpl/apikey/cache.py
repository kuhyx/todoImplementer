"""The newest key status the monitor saw, for code that must never wait on the network."""

from __future__ import annotations

import threading

from .keystatus import KeyStatus
from .store import read_key

_lock = threading.Lock()
_latest: KeyStatus | None = None


def put(current: KeyStatus | None) -> None:
    """Remember the newest status (None forgets it)."""
    global _latest  # noqa: PLW0603 - one process-wide value, guarded by the lock
    with _lock:
        _latest = current


def usable() -> tuple[bool, str]:
    """Return (can the key pay now, why not). Before the first check a readable key file counts as usable."""
    with _lock:
        seen = _latest
    if seen is None:
        found = read_key() is not None
        return found, "" if found else "no API key stored"
    return seen.usable, "" if seen.usable else f"API key {seen.state}: {seen.detail}"
