"""Claude Console API key lifecycle: store, live check, one status, a monitor. Stdlib only.

Part 2 (Agent-SDK turns on the monthly credits) needs only these two:

- `read_key() -> str | None`: the stored key, None when missing, empty or not shaped like `sk-ant-...`.
- `status() -> KeyStatus`: `state` (ok, expiring, expired, invalid, missing, check_failed), `expires`,
  `detail` and `usable` (ok or expiring). It makes one free GET /v1/models call; check `usable` first.
"""

from .keystatus import KeyStatus, status
from .store import read_key

__all__ = ["KeyStatus", "read_key", "status"]
