"""A fake OmniRoute: the real endpoints' shapes with made-up ids, names and a made-up masked key."""

from __future__ import annotations

import json
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

PASSWORD = "pw-secret-9"  # noqa: S105 - a made-up password
API_KEY = "sk-fake-key-123"
MASKED = "ab12cd34****ef56"  # what the real /api/providers shows of a key: it must never reach the page
SESSION = "sess-cookie-1"
NOW = 1_794_000_000.0  # a fixed "now" far from any real clock


def iso(epoch: float) -> str:
    """Return an ISO timestamp the way the gateway writes it."""
    return datetime.fromtimestamp(epoch, UTC).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def connection(name: str, **fields: Any) -> dict[str, Any]:
    """One provider connection as /api/providers lists it."""
    return {
        "id": f"id-{name}",
        "provider": name,
        "name": name,
        "isActive": True,
        "testStatus": "active",
        "backoffLevel": 0,
        "apiKey": MASKED,
        "providerSpecificData": {"accountId": "acct-77"},
        "quotaVisible": True,
        **fields,
    }


def world(now: float) -> dict[str, Any]:
    """Return the answers of every endpoint the monitor reads, at time `now`."""
    today = datetime.fromtimestamp(now, UTC).date().isoformat()
    cooling = {"apiKeyHealth": {"primary": {"cooldownUntil": iso(now + 90)}}, "accountId": "acct-77"}
    quota = {"used": 46, "total": 50, "remaining": 4, "resetAt": iso(now + 3600), "displayName": "daily"}
    return {
        "/api/v1/models/health": {"data": [{"id": "m1", "state": "ok"}, {"id": "m2", "state": "cooling"}]},
        "/api/providers": {
            "connections": [
                connection("nvidia"),
                connection("groq", providerSpecificData=cooling),
                connection("xkiro", testStatus="error"),
                connection("agnes", isActive=False),
                connection("openrouter"),
            ]
        },
        "/api/combos": {
            "combos": [
                {
                    "name": "free-best",
                    "models": [
                        {"id": "t1", "providerId": "nvidia", "model": "nvidia/nemotron"},
                        {"id": "t2", "providerId": "groq", "model": "groq/compound"},
                        {"id": "t3", "providerId": "openrouter", "model": "openrouter/x:free"},
                    ],
                }
            ]
        },
        "/api/combos/metrics": {
            "metrics": {
                "free-best": {
                    "totalRequests": 114,
                    "successRate": 99,
                    "fallbackRate": 36,
                    "byTarget": {
                        "t1": {
                            "requests": 48,
                            "successRate": 100,
                            "lastStatus": "ok",
                            "lastUsedAt": iso(now - 60),
                        },
                        "t3": {
                            "requests": 3,
                            "successRate": 0,
                            "lastStatus": "error",
                            "lastUsedAt": iso(now - 30),
                        },
                    },
                }
            }
        },
        "/api/usage/analytics?period=day": {
            "dailyTrend": [
                {"date": "2000-01-01", "requests": 1, "promptTokens": 1, "completionTokens": 1},
                {"date": today, "requests": 163, "promptTokens": 4_000_000, "completionTokens": 20_000},
            ]
        },
        "/api/usage/call-logs?limit=300": [
            {"timestamp": iso(now - 5), "tokens": {"in": 1000, "out": 10}},
            {"timestamp": iso(now - 5000), "tokens": {"in": 7, "out": 7}},
            {"timestamp": "garbage", "tokens": {"in": 7}},
            {"timestamp": iso(now - 5), "tokens": None},
            "not a call",
        ],
        "/api/usage/id-openrouter": {
            "plan": "free",
            "quotas": {
                "free_daily": quota,
                "credits": {"used": 0, "total": 0, "remaining": 0},
                "free_rpm": {"unlimited": True, "total": 20},
            },
        },
    }


class Handler(BaseHTTPRequestHandler):
    """The endpoints of the fake: login, Bearer-only /api/v1/*, cookie-only management paths."""

    server: Any

    def log_message(self, *_args: object) -> None:
        return

    def _reply(self, status: int, body: object) -> None:
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        gw: Gateway = self.server.gw
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        gw.requests.append((self.path, ""))
        if self.path != "/api/auth/login" or body.get("password") != PASSWORD:
            self._reply(401, {"error": "no"})
            return
        gw.logins += 1
        self.send_response(200)
        self.send_header("Set-Cookie", f"auth={SESSION}; Path=/")
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"{}")

    def _allowed(self, gw: Gateway) -> bool:
        bearer, cookie = self.headers.get("Authorization", ""), self.headers.get("Cookie", "")
        gw.requests.append((self.path, bearer or cookie))
        if self.path.startswith("/api/v1/"):
            return bearer == f"Bearer {API_KEY}"
        if SESSION in cookie and gw.denied:
            gw.denied -= 1
            return False
        return SESSION in cookie

    def do_GET(self) -> None:
        gw: Gateway = self.server.gw
        time.sleep(gw.delay)
        if not self._allowed(gw):
            self._reply(401, {"error": "no"})
        elif gw.garbage:
            self._reply(200, b"<html>")
        elif self.path in gw.answers:
            self._reply(200, gw.answers[self.path])
        else:
            self._reply(400, {"error": "no such thing"})


class Gateway:
    """Serve `answers` over HTTP; `denied` makes admin calls 401 that many times; `delay` slows answers."""

    def __init__(self, answers: dict[str, Any]) -> None:
        self.answers = answers
        self.requests: list[tuple[str, str]] = []  # (path, auth header or cookie seen)
        self.logins = 0
        self.denied = 0
        self.delay = 0.0
        self.garbage = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.gw = self  # type: ignore[attr-defined]
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self) -> None:
        """Shut the server down."""
        self.server.shutdown()
        self.server.server_close()


def wait_for(cond: object, timeout: float = 5.0) -> None:
    """Poll until `cond()` holds."""
    deadline = time.monotonic() + timeout
    while not cond():  # type: ignore[operator]
        assert time.monotonic() < deadline, "timed out waiting"
        time.sleep(0.01)
