r"""In-process fake of the todo app's MCP server (Streamable HTTP, bearer token, in-memory notes).

Import it with ``tests/shims`` on ``sys.path`` (``import fake_todo_mcp``); it mirrors
``~/src/todo/lib/mcp/`` closely enough that code tested against it works on the real server.

API::

    with FakeTodoMcp() as fake:                 # or fake.start() / fake.stop()
        fake.url                                # "http://127.0.0.1:<port>/mcp"
        fake.token                              # accepted bearer token ("test-token")
        note_id = fake.seed("kuhyx/demo", "demo todos", "## a\\nbody", priority="high",
                            done_check="true", status="todo")   # full id; repo=None = no-repo note
        fake.store.notes[note_id]               # FakeNote dataclass, mutate freely
        fake.calls                              # [(tool_name, arguments), ...] of every tools/call
        fake.methods                            # every JSON-RPC method received, in order
        fake.sessions                           # live Mcp-Session-Id values
        fake.seed_sections("kuhyx/demo", [("a", "text"), ("b", "")])   # multi-section note
        fake.fail_next(503)                     # next POST answers that HTTP status (any code)
        fake.force_text("list_tasks", "boom", is_error=True)   # next call of that tool replies so
        fake.force_raw(b"not json", "application/json")        # next POST answers this raw body
        fake.expire_sessions()                  # forget sessions: next request gets HTTP 404
        fake.fail_method("tools/call", 500)     # every request of that JSON-RPC method answers 500
        fake.fail_method("tools/call", None)    # ...until cleared

Constructor flags: ``token``, ``sse`` (reply as ``text/event-stream`` with a keep-alive comment and
a notification event before the answer, like a streaming server; default plain JSON), ``session``
(send ``Mcp-Session-Id``; default True).

Tools (same arguments, validation and texts as the real server): add_task, list_tasks, get_task,
update_task, close_task, search_tasks. Statuses on the wire are ``todo|in_progress|done|abandoned``.
Without a valid bearer token every POST answers 401. Behaviour pinned from the real server:
list_tasks never returns notes without ``repo``; add_task appends a ``## title`` section to the
repo's oldest open note; errors are ``isError`` results whose text starts with ``error: ``.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Self

from fake_todo_store import FakeStore, ToolError

_PROTOCOL = "2025-03-26"


class FakeTodoMcp:
    """Start/stop wrapper owning the server thread, the store and the injected faults."""

    def __init__(self, *, token: str = "test-token", sse: bool = False, session: bool = True) -> None:  # noqa: S107
        """Configure only; call ``start`` (or use ``with``) to listen on 127.0.0.1:0."""
        self.token, self.sse, self.session = token, sse, session
        self.store = FakeStore()
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.methods: list[str] = []
        self.sessions: set[str] = set()
        self._http_failures: list[int] = []
        self._forced_text: dict[str, tuple[str, bool]] = {}
        self._forced_raw: list[tuple[bytes, str]] = []
        self._method_failures: dict[str, int] = {}
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self.url = ""

    def seed(self, repo: str | None, title: str, body: str = "", **fields: str | None) -> str:
        """Insert a note directly (see ``FakeStore.seed``) and return its full id."""
        return self.store.seed(repo, title, body, **fields)

    def seed_sections(self, repo: str | None, sections: list[tuple[str, str]], **fields: str | None) -> str:
        """Insert a "<repo> todos" note whose body is one ``## title`` section per (title, body) pair."""
        body = "\n\n".join(f"## {title}\n{text}".rstrip() for title, text in sections)
        return self.store.seed(repo, f"{(repo or 'x').split('/')[-1]} todos", body, **fields)

    def fail_next(self, status: int) -> None:
        """Answer the next POST with this HTTP status and an empty body."""
        self._http_failures.append(status)

    def force_text(self, tool: str, text: str, *, is_error: bool = False) -> None:
        """Make the next ``tools/call`` of ``tool`` return this text instead of running it."""
        self._forced_text[tool] = (text, is_error)

    def force_raw(self, body: bytes, content_type: str = "application/json") -> None:
        """Make the next POST answer 200 with this raw body."""
        self._forced_raw.append((body, content_type))

    def fail_method(self, method: str, status: int | None) -> None:
        """Answer every request of this JSON-RPC ``method`` with ``status`` (None clears)."""
        if status is None:
            self._method_failures.pop(method, None)
        else:
            self._method_failures[method] = status

    def expire_sessions(self) -> None:
        """Forget every session id, as after a server restart."""
        self.sessions.clear()

    def start(self) -> Self:
        """Listen on a free loopback port in a daemon thread."""
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:
                fake._handle(self)

            def log_message(self, *_args: Any) -> None:
                """Keep test output quiet."""

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self._server.server_address[1]}/mcp"
        thread = threading.Thread(
            target=self._server.serve_forever,
            kwargs={"poll_interval": 0.01},
            daemon=True,
        )
        thread.start()
        return self

    def stop(self) -> None:
        """Shut the server down."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    def __enter__(self) -> Self:
        """Start listening."""
        return self.start()

    def __exit__(self, *_exc: object) -> None:
        """Stop listening."""
        self.stop()

    def _handle(self, req: BaseHTTPRequestHandler) -> None:
        length = int(req.headers.get("Content-Length") or 0)
        raw = req.rfile.read(length)
        with self._lock:
            status, ctype, body, extra = self._respond(dict(req.headers.items()), raw)
        try:
            req.send_response(status)
            req.send_header("Content-Type", ctype)
            req.send_header("Content-Length", str(len(body)))
            for key, value in extra.items():
                req.send_header(key, value)
            req.end_headers()
            req.wfile.write(body)
        except BrokenPipeError, ConnectionResetError:
            return

    def _respond(self, headers: dict[str, str], raw: bytes) -> tuple[int, str, bytes, dict[str, str]]:
        if self._http_failures:
            return self._http_failures.pop(0), "text/plain", b"", {}
        if headers.get("Authorization") != f"Bearer {self.token}":
            return 401, "text/plain", b"unauthorized", {}
        if self._forced_raw:
            body, ctype = self._forced_raw.pop(0)
            return 200, ctype, body, {}
        message = json.loads(raw)
        self.methods.append(message["method"])
        if message["method"] in self._method_failures:
            return self._method_failures[message["method"]], "text/plain", b"", {}
        sid = headers.get("Mcp-Session-Id")
        if message["method"] != "initialize" and self.session and sid not in self.sessions:
            return 404, "text/plain", b"unknown session", {}
        if "id" not in message:
            return 202, "text/plain", b"", {}
        if message["method"] == "initialize":
            return self._initialized(message)
        return self._frame(message["id"], self._dispatch(message), {})

    def _initialized(self, message: dict[str, Any]) -> tuple[int, str, bytes, dict[str, str]]:
        extra: dict[str, str] = {}
        if self.session:
            sid = f"fake-session-{len(self.sessions) + 1}-{threading.get_ident()}"
            self.sessions.add(sid)
            extra["Mcp-Session-Id"] = sid
        result = {
            "protocolVersion": _PROTOCOL,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "todo", "version": "1.0.0"},
        }
        return self._frame(message["id"], {"result": result}, extra)

    def _dispatch(self, message: dict[str, Any]) -> dict[str, Any]:
        if message["method"] == "ping":
            return {"result": {}}
        if message["method"] != "tools/call":
            return {"error": {"code": -32601, "message": f"method not found: {message['method']}"}}
        name, args = message["params"]["name"], message["params"].get("arguments") or {}
        self.calls.append((name, args))
        if name in self._forced_text:
            text, is_error = self._forced_text.pop(name)
            return {"result": {"content": [{"type": "text", "text": text}], "isError": is_error}}
        try:
            return {"result": {"content": [{"type": "text", "text": self.store.call(name, args)}]}}
        except ToolError as err:
            text = f"error: {err}"
            return {"result": {"content": [{"type": "text", "text": text}], "isError": True}}

    def _frame(
        self, rpc_id: int, payload: dict[str, Any], extra: dict[str, str]
    ) -> tuple[int, str, bytes, dict[str, str]]:
        envelope = json.dumps({"jsonrpc": "2.0", "id": rpc_id, **payload})
        if not self.sse:
            return 200, "application/json", envelope.encode(), extra
        note = json.dumps({"jsonrpc": "2.0", "method": "notifications/message", "params": {}})
        text = f": keep-alive\n\nevent: message\ndata: {note}\n\nevent: message\ndata: {envelope}\n\n"
        return 200, "text/event-stream; charset=utf-8", text.encode(), extra
