"""Paired phones: SHA-256 digests of device tokens in a 0600 file. Deleting the file revokes every device."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Callable

log = logging.getLogger("todoimpl.http")
TOUCH_EVERY = 3600  # last_seen moves at most once an hour per device, so a page load is not a disk write
MAX_TOKEN = 200  # a real token is 43 characters; longer is junk, refused before hashing
UA_CHARS = 80


def default_path() -> Path:
    """`$TODOIMPL_DEVICES`, else ~/.config/todoImplementer/devices.json."""
    given = os.environ.get("TODOIMPL_DEVICES")
    return Path(given) if given else Path.home() / ".config" / "todoImplementer" / "devices.json"


def digest(token: str) -> str:
    """Return the SHA-256 hex digest of a device token (the only form that is ever stored)."""
    return hashlib.sha256(token.encode()).hexdigest()


def _valid(entry: object) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("sha256"), str)
        and isinstance(entry.get("last_seen"), int)
    )


class DeviceStore:
    """The device list on disk; read on every check so deleting the file revokes at once."""

    def __init__(self, path: Path, clock: Callable[[], float] = time.time) -> None:
        """Keep the list in `path`; `clock` gives epoch seconds (tests inject one)."""
        self.path = path
        self.clock = clock
        self._lock = threading.Lock()

    def _load(self) -> list[dict[str, Any]]:
        """Return the stored entries; a missing or damaged file is an empty list (nobody is paired)."""
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return []
        except OSError, ValueError:
            log.warning("devices file unreadable; treating every device as unpaired")
            return []
        if not isinstance(data, list) or not all(_valid(entry) for entry in data):
            log.warning("devices file malformed; treating every device as unpaired")
            return []
        return data

    def _save(self, entries: list[dict[str, Any]]) -> None:
        atomic.write_text(self.path, json.dumps(entries, indent=1) + "\n", mode=0o600)

    def add(self, token: str, ua: str | None) -> None:
        """Remember a new device by the digest of its token."""
        now = int(self.clock())
        entry = {"sha256": digest(token), "created": now, "last_seen": now, "ua": (ua or "")[:UA_CHARS]}
        with self._lock:
            self._save([*self._load(), entry])

    def check(self, token: str) -> bool:
        """Return whether the token belongs to a paired device; touches last_seen at most hourly."""
        if not token or len(token) > MAX_TOKEN:
            return False
        wanted = digest(token).encode()
        with self._lock:
            entries = self._load()
            hit = None
            for entry in entries:  # every entry is compared: no early exit that leaks which one matched
                if hmac.compare_digest(str(entry["sha256"]).encode(), wanted):
                    hit = entry
            if hit is not None:
                now = int(self.clock())
                if now - int(hit["last_seen"]) >= TOUCH_EVERY:
                    hit["last_seen"] = now
                    self._save(entries)
            return hit is not None
