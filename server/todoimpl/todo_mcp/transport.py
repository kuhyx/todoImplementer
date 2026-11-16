"""Streamable-HTTP MCP transport: initialize, session id, bearer token, JSON or SSE replies."""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from itertools import count
from typing import Any

from todoimpl.todo_mcp.model import TodoError, UnreachableError

PROTOCOL = "2025-03-26"
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_AUTH_CODES = (401, 403)
_NOT_FOUND = 404
# A local service: a short ladder (seconds, capped at the last rung) so the board is fresh again soon
# after the todo app returns. Single-flight already keeps sockets from piling up. Not `retry.delay`.
LADDER = (1.0, 2.0, 5.0, 10.0, 30.0)


class Transport:
    """One MCP session over HTTP; thread-safe, re-initialises once if the session vanishes.

    Single-flight and backoff (T2005): one request is on the wire at a time; a timeout or connection error
    closes a gate for the next rung of `LADDER` (1, 2, 5, 10, 30 s), and calls inside it fail at once
    with `UnreachableError` and open no socket. A reply that gets through resets the ladder.
    """

    def __init__(
        self, url: str, token: str, timeout: float = 20.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Remember the endpoint; nothing is sent until the first call."""
        self.url = url
        self._token = token
        self._timeout = timeout
        self._session: str | None = None
        self._ready = False
        self._ids = count(1)
        self._lock = threading.Lock()
        self._io = threading.Lock()  # one request on the wire at a time
        self._clock = clock
        self._failures = 0
        self._retry_at = 0.0
        self._cause = ""

    def __repr__(self) -> str:
        """Show the url only, never the token."""
        return f"Transport({self.url!r})"

    def call_tool(self, name: str, arguments: dict[str, object]) -> str:
        """Run a tool and return its text; raises ``TodoError`` on any failure or ``isError``."""
        params = {"name": name, "arguments": arguments}
        try:
            result = self.request("tools/call", params)
        except _SessionGoneError:
            self._reset()
            try:
                result = self.request("tools/call", params)
            except _SessionGoneError as err:
                msg = "MCP session rejected again after re-initialising"
                raise TodoError(msg) from err
        return _tool_text(result)

    def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send one JSON-RPC request in an initialised session and return its ``result``."""
        self._ensure_ready()
        return self._rpc(method, params)

    def _reset(self) -> None:
        with self._lock:
            self._ready = False
            self._session = None

    def _ensure_ready(self) -> None:
        with self._lock:
            if self._ready:
                return
            init = {
                "protocolVersion": PROTOCOL,
                "capabilities": {},
                "clientInfo": {"name": "todoimpl", "version": "1"},
            }
            self._rpc("initialize", init)
            self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
            self._ready = True

    def _rpc(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        rpc_id = next(self._ids)
        body = {"jsonrpc": "2.0", "id": rpc_id, "method": method, "params": params}
        status, headers, payload = self._post(body)
        if method == "initialize" and (sid := headers.get("mcp-session-id")):
            self._session = sid
        if status == _NOT_FOUND and self._session is not None:
            raise _SessionGoneError
        message = _find_reply(payload, headers.get("content-type", ""), rpc_id)
        if "error" in message:
            err = message["error"]
            detail = err.get("message", err) if isinstance(err, dict) else err
            msg = f"MCP rpc error: {detail}"
            raise TodoError(msg)
        result = message.get("result")
        if not isinstance(result, dict):
            msg = f"MCP reply to {method} has no result"
            raise TodoError(msg)
        return result

    def _post(self, body: dict[str, Any]) -> tuple[int, dict[str, str], str]:
        with self._io:
            if self._failures and self._clock() < self._retry_at:
                raise UnreachableError(self._cause)  # inside the backoff: no socket
            return self._send(body)

    def _send(self, body: dict[str, Any]) -> tuple[int, dict[str, str], str]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
        }
        if self._session is not None:
            headers["Mcp-Session-Id"] = self._session
        request = urllib.request.Request(self.url, json.dumps(body).encode(), headers)  # noqa: S310
        try:
            with _OPENER.open(request, timeout=self._timeout) as resp:
                result = resp.status, _lower(resp.headers.items()), resp.read().decode()
        except urllib.error.HTTPError as err:
            status, headers_in = err.code, _lower(err.headers.items())
            err.close()
        except OSError as err:  # includes URLError and timeouts; the `with` above closed any response
            timed_out = isinstance(err, TimeoutError) or isinstance(
                getattr(err, "reason", None), TimeoutError
            )
            cause = "timeout" if timed_out else f"cannot reach MCP server at {self.url}: {err}"
            raise self._fail(cause) from err
        else:
            self._failures = 0
            return result
        if status == _NOT_FOUND and self._session is not None:
            return status, headers_in, ""
        if self._failures:  # an error from a server that was just not answering is not a verdict on the token
            raise self._fail("HTTP " + str(status) + " after timeouts")
        hint = " (token rejected)" if status in _AUTH_CODES else ""
        msg = f"MCP server answered HTTP {status}{hint}"
        raise TodoError(msg)

    def _fail(self, cause: str) -> UnreachableError:
        """Close the gate for the next rung of the ladder and build the honest error."""
        self._cause = f"todo MCP not answering ({cause})"
        self._retry_at = self._clock() + LADDER[min(self._failures, len(LADDER) - 1)]
        self._failures += 1
        return UnreachableError(self._cause)


class _SessionGoneError(Exception):
    """Internal: the server forgot our session id (HTTP 404)."""


def _lower(items: Iterable[tuple[str, str]]) -> dict[str, str]:
    return {key.lower(): value for key, value in items}


def _find_reply(payload: str, content_type: str, rpc_id: int) -> dict[str, Any]:
    candidates = _sse_events(payload) if content_type.startswith("text/event-stream") else [payload]
    for raw in candidates:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and parsed.get("id") == rpc_id:
            return parsed
    msg = f"unparseable MCP reply to request {rpc_id}: {payload[:80]!r}"
    raise TodoError(msg)


def _sse_events(payload: str) -> list[str]:
    events = []
    for block in payload.replace("\r\n", "\n").split("\n\n"):
        data = [line[5:].lstrip() for line in block.split("\n") if line.startswith("data:")]
        if data:
            events.append("\n".join(data))
    return events


def _tool_text(result: dict[str, Any]) -> str:
    content = result.get("content")
    if not isinstance(content, list):
        msg = "MCP tool result has bad content"
        raise TodoError(msg)
    texts = [item["text"] for item in content if isinstance(item, dict) and isinstance(item.get("text"), str)]
    if not texts:
        msg = "MCP tool result has no text"
        raise TodoError(msg)
    text = "\n".join(texts)
    if result.get("isError"):
        raise TodoError(text.removeprefix("error: "))
    return text
