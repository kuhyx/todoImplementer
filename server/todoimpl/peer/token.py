"""The peer endpoint's own token (a 0600 file in the run root) and each board card's key derived from it."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from typing import TYPE_CHECKING

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "peer.token"
KEY_FILE = "peer.key"  # in a card's run dir: that card's key, for its board session's MCP server


def ensure(root: Path) -> str:
    """Return the token, creating the file (mode 0600) on first use."""
    path = root / FILE
    try:
        found = path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        found = ""
    if not found:
        found = secrets.token_urlsafe(32)
        atomic.write_text(path, found + "\n", mode=0o600)
    return found


def derive(token: str, purpose: str) -> str:
    """HMAC-SHA256 of `purpose` under the token, hex."""
    return hmac.new(token.encode(), purpose.encode(), hashlib.sha256).hexdigest()


def card_key(token: str, card: str) -> str:
    """Return the key that lets a session speak as `task:<card>`."""
    return derive(token, f"card:{card}")


def same(given: str | None, expected: str) -> bool:
    """Constant-time comparison; a missing value never matches."""
    return given is not None and hmac.compare_digest(given.encode(), expected.encode())


def write_card_key(root: Path, card: str) -> Path:
    """Write the card's key into its run dir (0600) and return the path."""
    path = root / card / KEY_FILE
    atomic.write_text(path, card_key(ensure(root), card) + "\n", mode=0o600)
    return path
