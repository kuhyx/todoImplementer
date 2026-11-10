"""Read-only calls to the OmniRoute gateway, at most `TIMEOUT` seconds each; no secret in any message.

Two auth tiers (DOCS-tracking.md): the Bearer key from `~/.config/omniroute/api_key` opens
`/api/v1/models/health`; the management endpoints (`/api/providers`, `/api/combos*`, `/api/usage*`) need the
dashboard session, which `/api/auth/login` hands out for `~/.config/omniroute/admin_password` as a cookie. The
cookie jar lives in memory and a 401 or 403 logs in once more. `$TODOIMPL_OMNIROUTE_DIR` moves the two secret
files (tests).
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from todoimpl.runner import freegate

TIMEOUT = 2.0
DENIED = (401, 403)


class GatewayError(Exception):
    """A call failed; the text names the class of failure and never carries a URL query or a secret."""


def secret_dir() -> Path:
    """Return the directory holding `api_key` and `admin_password`."""
    return Path(os.environ.get("TODOIMPL_OMNIROUTE_DIR") or Path.home() / ".config" / "omniroute")


def _secret(name: str) -> str:
    try:
        text = (secret_dir() / name).read_text(encoding="utf-8").strip()
    except OSError as exc:
        msg = f"no {name} file"
        raise GatewayError(msg) from exc
    if not text:
        msg = f"{name} is empty"
        raise GatewayError(msg)
    return text


class Client:
    """One gateway: Bearer calls and cookie-session calls."""

    def __init__(self, base: str | None = None, timeout: float = TIMEOUT) -> None:  # noqa: D107
        self.base = (base or freegate.base_url()).rstrip("/")
        self.timeout = timeout
        self._jar = http.cookiejar.CookieJar()
        self._opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self._jar))
        self._logged_in = False

    def _send(self, path: str, body: object = None, headers: dict[str, str] | None = None) -> Any:  # noqa: ANN401
        data = None if body is None else json.dumps(body).encode()
        head = {"content-type": "application/json", **(headers or {})}
        request = urllib.request.Request(self.base + path, data=data, headers=head)  # noqa: S310 - loopback
        try:
            with self._opener.open(request, timeout=self.timeout) as reply:
                raw = reply.read()
        except urllib.error.HTTPError as exc:
            msg = f"HTTP {exc.code}"
            raise GatewayError(msg) from exc
        except OSError as exc:  # refused, unreachable, timed out
            msg = f"unreachable ({type(exc).__name__})"
            raise GatewayError(msg) from exc
        try:
            return json.loads(raw) if raw else {}
        except ValueError as exc:
            msg = "not JSON"
            raise GatewayError(msg) from exc

    def bearer(self, path: str) -> Any:  # noqa: ANN401
        """GET with the API key."""
        return self._send(path, headers={"Authorization": f"Bearer {_secret('api_key')}"})

    def admin(self, path: str) -> Any:  # noqa: ANN401
        """GET with the dashboard session; log in first, and again once when the session was refused."""
        if not self._logged_in:
            self._login()
        try:
            return self._send(path)
        except GatewayError as exc:
            if not any(str(code) in str(exc) for code in DENIED):
                raise
        self._login()
        return self._send(path)

    def _login(self) -> None:
        self._send("/api/auth/login", {"password": _secret("admin_password")})
        self._logged_in = True
