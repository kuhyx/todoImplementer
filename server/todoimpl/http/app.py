"""ThreadingHTTPServer wiring: one Handler class that only moves bytes between sockets and the Router."""

from __future__ import annotations

import contextlib
import logging
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from . import upload
from .auth import DEFAULT_ORIGINS, new_token
from .device_gate import Admission, Gate
from .reply import Reply
from .routes import Router, SseReply
from .sse import stream
from .static import StaticSite

if TYPE_CHECKING:
    from .backend import Backend

log = logging.getLogger("todoimpl.http")
DEFAULT_DIST = Path(__file__).resolve().parents[3] / "web" / "dist"
LOOPBACK = ("127.0.0.1", "localhost")
DRAIN_LIMIT = 2 * 1024 * 1024
IDLE_TIMEOUT = 30


class AppServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that carries its Router and the SSE keepalive interval."""

    daemon_threads = True
    router: Router
    gate: Gate
    heartbeat: float = 15.0  # seconds between SSE keepalives; tests shorten it


class Handler(BaseHTTPRequestHandler):
    """Reads one request, asks the Router, writes the Reply or the event stream."""

    server: AppServer
    protocol_version = "HTTP/1.1"
    timeout = IDLE_TIMEOUT

    def do_GET(self) -> None:
        """GET: API, SSE or static."""
        self._guarded(self._get)

    def do_POST(self) -> None:
        """POST: an action."""
        self._guarded(self._post)

    def _guarded(self, step: Any) -> None:  # noqa: ANN401 - a bound method
        try:
            step()
        except BrokenPipeError, ConnectionResetError:
            log.debug("client went away during %s %s", self.command, self.path)
            self.close_connection = True

    def _admit(self) -> Admission | None:
        """Gate the request; a refused one is answered here and gives None."""
        hosts = self.headers.get_all("Host", [])
        verdict = self.server.gate.admit(self.command, self.path, hosts, self.headers.get_all("Cookie", []))
        if isinstance(verdict, Admission):
            return verdict
        self._send(verdict)
        return None

    def _get(self) -> None:
        if (access := self._admit()) is None:
            return
        gate = self.server.gate
        if gate.serves("GET", self.path):
            self._send(gate.redeem(self.path, (self.headers.get("User-Agent") or "")))
            return
        reply = self.server.router.get(self.path, self.headers.get("Last-Event-ID"), local=access.local)
        if isinstance(reply, SseReply):
            self._sse(reply)
        else:
            self._send(gate.renew(reply, access))

    def _post(self) -> None:
        if (access := self._admit()) is None:
            return
        router = self.server.router
        if self.server.gate.serves("POST", self.path):
            reply = self.server.gate.mint(
                access,
                self.headers.get("Origin"),
                self.headers.get("X-Todoimpl-Token"),
                expected=router.token,
                origins=router.origins,
            )
            self._send(reply)
            return
        if urlsplit(self.path).path == upload.PATH:  # streamed to disk, never read into memory
            self._send(upload.handle(router.token, router.origins, self.headers, self.rfile.read))
            return
        reply = router.post(
            self.path,
            self.headers.get("Origin"),
            self.headers.get("X-Todoimpl-Token"),
            self.headers.get("Content-Length"),
            self.rfile.read,
        )
        self._send(reply)

    def _send(self, reply: Reply) -> None:
        self.send_response(reply.status)
        self.send_header("Content-Type", reply.ctype)
        self.send_header("Content-Length", str(len(reply.body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        for name, value in reply.headers:
            self.send_header(name, value)
        if reply.close:
            self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(reply.body)
        if reply.close:
            self.close_connection = True
            self._drain()

    def _drain(self) -> None:
        """Swallow what the client is still sending so closing does not RST away our answer."""
        with contextlib.suppress(OSError):
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            left = DRAIN_LIMIT
            while left > 0 and (chunk := self.connection.recv(65536)):
                left -= len(chunk)

    def _sse(self, reply: SseReply) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Accel-Buffering", "no")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True

        def write(chunk: bytes) -> None:
            self.wfile.write(chunk)
            self.wfile.flush()

        stream(write, reply.snapshot, reply.events, reply.last_seq, self.server.heartbeat)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002, ANN401 - stdlib signature
        """Access log through logging, not stderr."""
        log.info("%s %s", self.address_string(), format % args)


def make_server(  # noqa: PLR0913 - bind address, site and build, all keyword seams
    backend: Backend,
    host: str = "127.0.0.1",
    port: int = 8786,
    *,
    dist: Path = DEFAULT_DIST,
    build: str = "unknown",
    build_name: str | None = None,
) -> AppServer:
    """Bind a server on a loopback address; the bound loopback origin is always an allowed Origin."""
    if host not in LOOPBACK:
        msg = f"refusing to bind {host!r}: the server is loopback only"
        raise ValueError(msg)
    server = AppServer((host, port), Handler)
    token = new_token()
    origins = (*DEFAULT_ORIGINS, f"http://127.0.0.1:{server.server_address[1]}")
    server.gate = Gate.create(server.server_address[1])
    server.router = Router(
        backend, StaticSite(dist, token, build, build_name), token=token, origins=origins, build=build
    )
    return server
