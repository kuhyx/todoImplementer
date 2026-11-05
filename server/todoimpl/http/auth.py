"""CSRF defence for every POST: same-origin Origin header plus a per-start random token."""

from __future__ import annotations

import hmac
import secrets

DEFAULT_ORIGINS = ("http://127.0.0.1:8786", "https://agents.kuhy.duckdns.org")


def new_token() -> str:
    """Return a fresh random CSRF token (one per server start)."""
    return secrets.token_urlsafe(32)


def check_post(
    origin: str | None, token: str | None, *, expected: str, origins: tuple[str, ...]
) -> str | None:
    """Return why the POST must be refused, or None when Origin and token are both right."""
    if origin not in origins:
        return "bad origin"
    if token is None or not hmac.compare_digest(token.encode(), expected.encode()):
        return "bad token"
    return None
