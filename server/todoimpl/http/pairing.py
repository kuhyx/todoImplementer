"""One-time pairing codes kept in server memory: a restart drops them, which is fine."""

from __future__ import annotations

import hmac
import secrets
import threading
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

CODE_TTL = 300  # seconds a code stays redeemable
MAX_PENDING = 5  # minting a sixth drops the oldest


class PairCodes:
    """Mint codes the PC page shows as a QR; the phone redeems each exactly once."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        """`clock` gives epoch seconds (tests inject one)."""
        self.clock = clock
        self._pending: dict[str, float] = {}  # code -> expiry, oldest first
        self._lock = threading.Lock()

    def _drop_expired(self) -> None:
        now = self.clock()
        for code in [c for c, expiry in self._pending.items() if expiry <= now]:
            del self._pending[code]

    def mint(self) -> tuple[str, int]:
        """Return a fresh code and the epoch second it dies at."""
        with self._lock:
            self._drop_expired()
            while len(self._pending) >= MAX_PENDING:
                del self._pending[next(iter(self._pending))]
            code = secrets.token_urlsafe(16)
            expiry = self.clock() + CODE_TTL
            self._pending[code] = expiry
            return code, int(expiry)

    def redeem(self, code: str | None) -> bool:
        """Consume the code and return True when it was pending and unexpired."""
        if not code:
            return False
        wanted = code.encode()
        with self._lock:
            self._drop_expired()
            hit = None
            for pending in self._pending:  # compare against all of them, constant-time each
                if hmac.compare_digest(pending.encode(), wanted):
                    hit = pending
            if hit is None:
                return False
            del self._pending[hit]
            return True
