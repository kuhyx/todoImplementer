"""One KeyStatus from the key file, its metadata and the live check (what the monitor and the board show)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

from . import store
from .verify import Verdict, verify

State = Literal["ok", "expiring", "expired", "invalid", "missing", "check_failed"]
WARN_DAYS = 3
ROTATE_COMMAND = "~/src/todoImplementer/scripts/rotate_api_key.py"
LEVELS: dict[str, str] = {
    "ok": "ok",
    "expiring": "warn",
    "expired": "error",
    "invalid": "error",
    "missing": "error",
    "check_failed": "error",
}


@dataclass(frozen=True)
class KeyStatus:
    """`state` is one of ok, expiring, expired, invalid, missing, check_failed; `detail` is plain text."""

    state: State
    expires: date | None
    detail: str

    @property
    def usable(self) -> bool:
        """True when a turn may use the key (ok, or expiring but still valid)."""
        return self.state in ("ok", "expiring")


def status(*, today: date | None = None, check: Callable[[str], Verdict] | None = None) -> KeyStatus:
    """Combine file presence, key format, recorded expiry and the live check (one GET, no tokens)."""
    today = today or date.today()  # noqa: DTZ011 - the local calendar day is what kuhy sees in the Console
    live = check or verify
    raw = store.read_raw()
    if raw is None:
        return KeyStatus("missing", None, f"no key in {store.key_path()}")
    if not store.is_key(raw):
        return KeyStatus("invalid", None, "the stored key has the wrong format")
    meta = store.read_meta()
    expires = meta.expires if meta else None
    if expires is not None and expires < today:
        return KeyStatus("expired", expires, f"expired on {expires}")
    return _judge(live(raw), expires, today)


def _judge(verdict: Verdict, expires: date | None, today: date) -> KeyStatus:
    """Turn the live verdict plus the recorded expiry into the status of a key that is not yet expired."""
    if verdict.outcome == "invalid":
        return KeyStatus("invalid", expires, f"rejected by the API ({verdict.detail}): expired or revoked")
    if verdict.outcome == "check_failed":
        return KeyStatus("check_failed", expires, f"could not check the key: {verdict.detail}")
    if expires is None:
        return KeyStatus("ok", None, "valid (expiry not recorded)")
    left = (expires - today).days
    if left <= WARN_DAYS:
        return KeyStatus("expiring", expires, f"valid, expires on {expires} ({left} days left)")
    return KeyStatus("ok", expires, f"valid, expires on {expires}")


def board_field(current: KeyStatus) -> dict[str, Any]:
    """Return the `api_key` object of /api/board: the server words the banner, the page only shows it."""
    level = LEVELS[current.state]
    text = f"Claude API key {current.state.replace('_', ' ')}: {current.detail}"
    if level != "ok":
        text += f". Run {ROTATE_COMMAND}"
    return {
        "state": current.state,
        "level": level,
        "text": text,
        "expires": current.expires.isoformat() if current.expires else None,
    }
