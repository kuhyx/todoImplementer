"""Helpers for the phone-access tests: public and local requests over a real socket."""

import socket
from urllib.parse import parse_qs, urlsplit

from httpfakes import Live, Reply, call

PUBLIC = "agents.kuhy.duckdns.org"
COOKIE = "todoimpl_device"


def public(live: Live, method: str, path: str, cookie: str | None = None, **hdr: str) -> Reply:
    """Send a request as Caddy forwards it: public Host (no peer-address or forwarded-header tricks)."""
    headers = {"Host": PUBLIC, **hdr}
    if cookie is not None:
        headers["Cookie"] = f"{COOKIE}={cookie}"
    return call(live.port, method, path, None, headers)


def public_post(live: Live, path: str, cookie: str | None = None, **hdr: str) -> Reply:
    """Send a POST with good Origin and CSRF but a public Host."""
    headers = {**live.post_headers(), "Host": PUBLIC, **hdr}
    if cookie is not None:
        headers["Cookie"] = f"{COOKIE}={cookie}"
    return call(live.port, "POST", path, {}, headers)


def raw_get(live: Live, path: str, header_lines: str) -> bytes:
    """Send hand-written headers (no automatic Host) and return the whole answer."""
    with socket.create_connection(("127.0.0.1", live.port), timeout=5) as sock:
        sock.sendall(f"GET {path} HTTP/1.1\r\n{header_lines}Connection: close\r\n\r\n".encode())
        chunks = []
        while chunk := sock.recv(65536):
            chunks.append(chunk)
    return b"".join(chunks)


def mint_url(live: Live) -> str:
    """Ask the PC page for a pairing link, the way the QR button does."""
    reply = call(live.port, "POST", "/api/pair", {}, live.post_headers())
    assert reply.status == 200
    url: str = reply.json()["url"]
    return url


def pair(live: Live, ua: str = "TestPhone/1") -> str:
    """Pair a device through the real flow and return its cookie token."""
    code = parse_qs(urlsplit(mint_url(live)).query)["c"][0]
    done = public(live, "GET", f"/pair?c={code}", **{"User-Agent": ua})
    assert done.status == 303
    return token_of(done)


def token_of(reply: Reply) -> str:
    """Return the device token from a Set-Cookie header."""
    first = reply.headers["set-cookie"].split(";")[0]
    name, _, value = first.partition("=")
    assert name == COOKIE
    return value
