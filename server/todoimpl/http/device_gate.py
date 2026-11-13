"""Gate for public requests: a request is public unless its Host is the bound loopback origin.

Caddy and the browser on the PC both reach the server from 127.0.0.1, so the peer address and every
X-Forwarded-* header say nothing. Caddy passes the visitor's Host through, so the Host header is the one
signal that tells them apart. A public request needs the per-device cookie (DOCS-phone.md).
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

from .auth import PUBLIC_ORIGIN, check_post
from .devices_store import MAX_TOKEN, DeviceStore, default_path
from .pairing import PairCodes
from .reply import JSON_TYPE, Reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Sequence

COOKIE = "todoimpl_device"
MAX_AGE = 34_560_000  # 400 days, the longest Chrome keeps a cookie
PAIR_PATH = "/pair"
API_PAIR_PATH = "/api/pair"
EXEMPT_PATHS = frozenset({PAIR_PATH, "/manifest.webmanifest", "/favicon.svg"})
# Flat image file names only: no slash, no leading dot, no percent, and never a page (an .html would be
# stamped with the CSRF token), so the exemption cannot be walked out of or used to read one.
ICON_PATH = re.compile(r"/icons/[A-Za-z0-9_-][A-Za-z0-9._-]*\.(?:png|webp|svg|ico|jpe?g)")
NO_STORE = ("Cache-Control", "no-store")


@dataclass(frozen=True)
class Admission:
    """Who is asking: local (the PC) or public, and the valid device token a public request carried."""

    local: bool
    token: str | None = None


def is_local(host: str | None, port: int) -> bool:
    """Return whether Host names the bound loopback origin exactly (case-insensitive, port required)."""
    if host is None:
        return False
    return host.lower() in {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}


def device_tokens(cookie_headers: Sequence[str]) -> list[str]:
    """Return every `todoimpl_device` value in the Cookie headers (a stuffed request may carry several)."""
    found = []
    for line in cookie_headers:
        for part in line.split(";"):
            name, _, value = part.strip().partition("=")
            if name == COOKIE and 0 < len(value) <= MAX_TOKEN:
                found.append(value)
    return found


def _refusal(*, close: bool) -> Reply:
    return Reply(401, b'{"error":"unauthorized"}', JSON_TYPE, (NO_STORE,), close)


def _plain(status: int, headers: tuple[tuple[str, str], ...] = (), *, close: bool = False) -> Reply:
    """Build a tiny answer with no words: the status code says it all."""
    return Reply(status, b"", "text/plain; charset=utf-8", (NO_STORE, *headers), close)


def cookie_line(token: str) -> tuple[str, str]:
    """Return the Set-Cookie header that stores (or renews) a device token for the full 400 days."""
    return ("Set-Cookie", f"{COOKIE}={token}; Max-Age={MAX_AGE}; Path=/; Secure; HttpOnly; SameSite=Lax")


class Gate:
    """Decides local or public, checks the device cookie, mints and redeems pairing codes."""

    def __init__(self, store: DeviceStore, codes: PairCodes, port: int, public_origin: str) -> None:
        """Gate a server bound to loopback `port`; pairing links point at `public_origin`."""
        self.store = store
        self.codes = codes
        self.port = port
        self.public_origin = public_origin

    @classmethod
    def create(cls, port: int) -> Gate:
        """Build the real gate: the device file under ~/.config, the public origin from the env or auth.py."""
        origin = os.environ.get("TODOIMPL_PUBLIC_ORIGIN") or PUBLIC_ORIGIN
        return cls(DeviceStore(default_path()), PairCodes(), port, origin)

    def admit(
        self, method: str, target: str, hosts: Sequence[str], cookies: Sequence[str]
    ) -> Admission | Reply:
        """Return who is asking, or the 401 to send when a public request has no paired-device cookie."""
        local = len(hosts) == 1 and is_local(hosts[0], self.port) and target.startswith("/")
        if local:
            return Admission(local=True)
        path = urlsplit(target).path
        if method == "GET" and (path in EXEMPT_PATHS or ICON_PATH.fullmatch(path)):
            return Admission(local=False)
        if method == "POST" and path == API_PAIR_PATH:  # minting is the PC's alone, cookie or not
            return _plain(403, close=True)
        for token in device_tokens(cookies):
            if self.store.check(token):
                return Admission(local=False, token=token)
        return _refusal(close=method == "POST")

    @staticmethod
    def serves(method: str, target: str) -> bool:
        """Return whether the gate answers this request itself (redeem on GET, mint on POST)."""
        return (method, urlsplit(target).path) in {("GET", PAIR_PATH), ("POST", API_PAIR_PATH)}

    def redeem(self, target: str, user_agent: str | None) -> Reply:
        """GET /pair?c=<code>: spend the code, store a new device, send it home with its cookie."""
        codes = parse_qs(urlsplit(target).query).get("c", [])
        if len(codes) != 1 or not self.codes.redeem(codes[0]):
            return _plain(403)
        token = secrets.token_urlsafe(32)
        self.store.add(token, user_agent)
        return _plain(303, (("Location", "/"), cookie_line(token)))

    def mint(
        self,
        access: Admission,
        origin: str | None,
        csrf: str | None,
        *,
        expected: str,
        origins: tuple[str, ...],
    ) -> Reply:
        """POST /api/pair: a pairing link, for the PC only, behind the usual Origin and CSRF checks."""
        if not access.local or check_post(origin, csrf, expected=expected, origins=origins) is not None:
            return _plain(403, close=True)
        code, expires_at = self.codes.mint()
        reply = json_reply({"url": f"{self.public_origin}{PAIR_PATH}?c={code}", "expires_at": expires_at})
        return Reply(reply.status, reply.body, reply.ctype, reply.headers, close=True)

    @staticmethod
    def renew(reply: Reply, access: Admission) -> Reply:
        """Re-send the cookie with a full Max-Age on a public page load, so a phone in use never expires."""
        if access.token is None or reply.status != HTTPStatus.OK or not reply.ctype.startswith("text/html"):
            return reply
        return Reply(reply.status, reply.body, reply.ctype, (*reply.headers, cookie_line(access.token)))
