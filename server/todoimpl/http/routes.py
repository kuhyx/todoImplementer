"""Routing and request handling, free of sockets: strings and bytes in, Reply or SseReply out."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from todoimpl.tokens_api import router as tokens_api
from todoimpl.version import __version__

from . import bodies
from .auth import check_post
from .backend import ERROR_CODES, BackendError
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .backend import Backend
    from .static import StaticSite

log = logging.getLogger("todoimpl.http")
CARD_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")  # <note id8>-<section index>, contracts item_id
SHOT_NAME = re.compile(r"[\w.-]+\.png", re.ASCII)
TASK_PATH = re.compile(r"/api/task/([^/]+)")
SHOT_PATH = re.compile(r"/api/task/([^/]+)/shot/([^/]+)")
ACTION_PATH = re.compile(r"/api/task/([^/]+)/([a-z-]+)")
MAX_BODY = 256 * 1024
SNAPSHOT_KEYS = ("stage", "status", "column", "current", "needs", "actions")


@dataclass(frozen=True)
class SseReply:
    """An event stream: the connect snapshot, then the live source, skipping activity up to last_seq."""

    snapshot: dict[str, Any]
    events: Iterator[dict[str, Any]]
    last_seq: int


def _guard(call: Callable[[], Reply | SseReply]) -> Reply | SseReply:
    """Turn backend refusals and crashes into contract errors; crashes never leak their text."""
    try:
        return call()
    except BackendError as exc:
        code = exc.code if exc.code in ERROR_CODES else "internal"
        return error_reply(code, exc.message)
    except Exception:
        log.exception("request failed")
        return error_reply("internal", "internal error")


def _last_seq(header: str | None) -> int:
    try:
        return max(int(header or 0), 0)
    except ValueError:
        return 0


class Router:
    """Maps requests onto the Backend and the static site."""

    def __init__(
        self, backend: Backend, site: StaticSite, *, token: str, origins: tuple[str, ...], build: str
    ) -> None:
        """Wire the collaborators; token and origins gate every POST."""
        self.backend = backend
        self.site = site
        self.token = token
        self.origins = origins
        self.build = build
        self._simple: dict[str, Callable[[], Reply]] = {
            "/version": lambda: json_reply({"build": self.build, "version": __version__}),
            "/api/board": lambda: json_reply(self.backend.board()),
            "/api/usage": lambda: json_reply(self.backend.usage()),
        }

    # ---- GET ----
    def get(self, target: str, last_event_id: str | None = None) -> Reply | SseReply:
        """Answer a GET: API route, SSE feed or static file."""
        parts = urlsplit(target)
        path = parts.path
        if path == "/api/live":
            return _guard(lambda: self._live(parse_qs(parts.query), _last_seq(last_event_id)))
        if path in self._simple:
            return _guard(self._simple[path])
        if path == tokens_api.PREFIX or path.startswith(tokens_api.PREFIX + "/"):
            return _guard(lambda: self._tokens(path, parts.query))
        if (reply := self._task_route(path)) is not None:
            return reply
        if not path.startswith("/api/") and (static := self.site.serve(path)) is not None:
            return static
        return error_reply("not_found", "no such route")

    def _task_route(self, path: str) -> Reply | SseReply | None:
        """Answer /api/task/<id> and its screenshots; None when path is neither."""
        if match := SHOT_PATH.fullmatch(path):
            return _guard(partial(self._shot, *match.groups()))
        if match := TASK_PATH.fullmatch(path):
            return _guard(lambda: self._task(match.group(1)))
        return None

    @staticmethod
    def _tokens(path: str, query: str) -> Reply:
        """Serve the token-spend API; it owns its own status codes and body shapes."""
        status, body = tokens_api.handle(path, query)
        return json_reply(body, int(status))

    def _task(self, id8: str) -> Reply:
        if not CARD_ID.fullmatch(id8):
            return error_reply("bad_request", "task id must look like abcd1234-0")
        detail = self.backend.task(id8)
        if detail is None:
            return error_reply("not_found", "unknown task")
        return json_reply(detail)

    def _shot(self, id8: str, name: str) -> Reply:
        if not CARD_ID.fullmatch(id8):
            return error_reply("bad_request", "task id must look like abcd1234-0")
        data = self.backend.shot(id8, name) if SHOT_NAME.fullmatch(name) else None
        if data is None:
            return error_reply("not_found", "no such screenshot")
        return Reply(200, data, "image/png", (("Cache-Control", "no-cache"),))

    def _live(self, query: dict[str, list[str]], last_seq: int) -> Reply | SseReply:
        ids = query.get("id", [])
        if len(ids) != 1 or not CARD_ID.fullmatch(ids[0]):
            return error_reply("bad_request", "exactly one task id (abcd1234-0) is required")
        detail = self.backend.task(ids[0])
        if detail is None:
            return error_reply("not_found", "unknown task")
        card = detail["card"]
        snapshot = {"type": "stage", **{key: card[key] for key in SNAPSHOT_KEYS}}
        return SseReply(snapshot, self.backend.subscribe(ids[0]), last_seq)

    # ---- POST ----
    def post(
        self,
        target: str,
        origin: str | None,
        token: str | None,
        length: str | None,
        read: Callable[[int], bytes],
    ) -> Reply:
        """Answer a POST. read(n) pulls the body; it is only called for a sane Content-Length."""
        try:
            size = int(length or 0)
        except ValueError:
            return error_reply("bad_request", "bad Content-Length", close=True)
        if size < 0 or size > MAX_BODY:
            return error_reply("bad_request", "request body too large or invalid length", close=True)
        raw = read(size) if size else b""
        if (why := check_post(origin, token, expected=self.token, origins=self.origins)) is not None:
            return error_reply("forbidden", why)
        reply = _guard(lambda: self._action(urlsplit(target).path, raw))
        assert isinstance(reply, Reply)  # noqa: S101 - _action never returns a stream
        return reply

    def _request(self, path: str, raw: bytes) -> tuple[str, str, dict[str, Any]] | Reply:
        """Resolve route, task id and body into (id8, action, body), or the refusal to send."""
        match = ACTION_PATH.fullmatch(path)
        if match is None or match.group(2) not in bodies.ACTIONS:
            return error_reply("not_found", "no such route")
        id8, action = match.groups()
        if not CARD_ID.fullmatch(id8):
            return error_reply("bad_request", "task id must look like abcd1234-0")
        body = self._parse(raw)
        if isinstance(body, str):
            return error_reply("bad_request", body)
        if (problem := bodies.check(action, body)) is not None:
            return error_reply("bad_request", problem)
        return id8, action, body

    def _action(self, path: str, raw: bytes) -> Reply:
        request = self._request(path, raw)
        if isinstance(request, Reply):
            return request
        id8, action, body = request
        detail = self.backend.task(id8)
        if detail is None:
            return error_reply("not_found", "unknown task")
        offered = next((a for a in detail["card"]["actions"] if a["id"] == action), None)
        if offered is None or not offered["enabled"]:
            reason = offered["reason"] if offered else None
            return error_reply("disabled", reason or "action not available")
        if body.get("auto_ship") is True and not (option := offered.get("option") or {}).get("enabled"):
            return error_reply("disabled", option.get("reason") or "Auto-ship is not offered here")
        self._invoke(action, id8, body)
        fresh = self.backend.task(id8) or detail
        return json_reply({"ok": True, "task": fresh["card"]})

    @staticmethod
    def _parse(raw: bytes) -> dict[str, Any] | str:
        try:
            body = json.loads(raw) if raw else {}
        except ValueError:
            return "body is not valid JSON"
        return body if isinstance(body, dict) else "body must be a JSON object"

    def _invoke(self, action: str, id8: str, body: dict[str, Any]) -> None:
        backend = self.backend
        match action:
            case "start":
                backend.start(id8, auto_ship=body.get("auto_ship"))
            case "spec-answers":
                backend.spec_answers(id8, body["answers"])
            case "spec-ok":
                backend.spec_ok(id8)
            case "send":
                backend.send(id8, body["text"])
            case "ship":
                backend.ship(id8)
            case "cancel":
                backend.cancel(id8)
            case "credits":
                backend.credits(id8)
            case _:
                backend.lesson_approve(id8, body["lesson_id"])
