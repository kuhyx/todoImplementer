"""Tiny HTTP client for the real server: same-origin Origin plus the CSRF token from the page."""

from __future__ import annotations

import http.client
import json
import re
import urllib.error
import urllib.request
from typing import Any

META = re.compile(r'<meta name="todoimpl-csrf" content="([^"]+)"')
PLACEHOLDER = "__TODOIMPL_CSRF__"


class Client:
    """GET/POST against 127.0.0.1:<port>; replies are (status, parsed JSON or text)."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.base = f"http://127.0.0.1:{port}"
        self._token: str | None = None

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
        """One request; HTTP errors come back as their status and body, never raise."""
        headers = {"Origin": self.base}
        data = None
        if method == "POST":
            headers["X-Todoimpl-Token"] = self.token()
            headers["Content-Type"] = "application/json"
            data = json.dumps(body or {}).encode()
        req = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)  # noqa: S310
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310 - loopback URL
                status, raw, ctype = resp.status, resp.read(), resp.headers.get("Content-Type", "")
        except urllib.error.HTTPError as err:
            status, raw, ctype = err.code, err.read(), err.headers.get("Content-Type", "")
        text = raw.decode("utf-8", errors="replace")
        return status, json.loads(text) if "json" in ctype else text

    def get(self, path: str) -> Any:
        """GET and require 200; return the parsed body."""
        status, body = self.request("GET", path)
        if status != 200:
            msg = f"GET {path} -> {status}: {str(body)[:300]}"
            raise AssertionError(msg)
        return body

    def post(self, path: str, body: dict[str, Any] | None = None) -> Any:
        """POST and require 200; return the parsed body."""
        status, reply = self.request("POST", path, body)
        if status != 200:
            msg = f"POST {path} -> {status}: {str(reply)[:300]}"
            raise AssertionError(msg)
        return reply

    def token(self) -> str:
        """Return the CSRF token the page carries."""
        if self._token is None:
            status, page = self.request("GET", "/")
            found = META.findall(page) if status == 200 and isinstance(page, str) else []
            if not found:
                msg = f"GET / -> {status}: no todoimpl-csrf meta tag (is web/dist built?)"
                raise AssertionError(msg)
            # The server appends its stamped tag; a built page may still carry the placeholder first.
            self._token = found[-1]
        return self._token

    def csrf_metas(self) -> list[str]:
        """Return the content of every todoimpl-csrf meta tag in the served page."""
        page = self.request("GET", "/")[1]
        return META.findall(page) if isinstance(page, str) else []

    def first_event(self, path: str, timeout: float = 5.0) -> dict[str, Any]:
        """Read an SSE stream until its first `data:` frame and return it parsed."""
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)
        try:
            conn.request("GET", path, headers={"Origin": self.base})
            resp = conn.getresponse()
            if resp.status != 200:
                msg = f"GET {path} -> {resp.status}: {resp.read()[:300]!r}"
                raise AssertionError(msg)
            while line := resp.readline():
                if line.startswith(b"data:"):
                    event: dict[str, Any] = json.loads(line[5:])
                    return event
        finally:
            conn.close()
        msg = f"GET {path}: stream ended without a data frame"
        raise AssertionError(msg)
