"""Routing and request handling, free of sockets: strings and bytes in, Reply or SseReply out."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, urlsplit

from todoimpl.sessions.commands import CommandRunner, SubprocessRunner
from todoimpl.tokens_api import router as tokens_api
from todoimpl.version import __version__

from . import asks as asks_http
from . import bodies, getroutes, issues, newtask, settings
from . import merge as merge_http
from . import sessions as sessions_http
from .auth import check_post
from .backend import ERROR_CODES, BackendError
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from .backend import Backend
    from .static import StaticSite

log = logging.getLogger("todoimpl.http")
CARD_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")  # <note id8>-<section index>, contracts item_id
SHOT_NAME = re.compile(r"(?:(?!\.{1,2}/)[\w.-]+/)*[\w.-]+\.png", re.ASCII)  # a/b.png, no dot segments
TASK_PATH = re.compile(r"/api/task/([^/]+)")
SHOT_PATH = re.compile(r"/api/task/([^/]+)/shot/(.+)")
ACTION_PATH = re.compile(r"/api/task/([^/]+)/([a-z-]+)")
MAX_BODY = 256 * 1024
SNAPSHOT_KEYS = ("stage", "status", "column", "current", "needs", "actions")


@dataclass(frozen=True)
class SseReply:
    """An event stream: the connect snapshot, then the live source, skipping activity up to last_seq."""

    snapshot: dict[str, Any]
    events: Iterator[dict[str, Any]]
    last_seq: int
    floor: int = 0  # the newest activity seq of an earlier cycle: a mirror drops what it holds (T2479)


def _guard[R: Reply | SseReply](call: Callable[[], R]) -> R | Reply:
    """Turn backend refusals and crashes into contract errors; crashes never leak their text."""
    try:
        return call()
    except BackendError as exc:
        return error_reply(exc.code if exc.code in ERROR_CODES else "internal", exc.message)
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
            sessions_http.GET_PATH: lambda: sessions_http.listing(self),
        }
        self.sessions_runner: CommandRunner = SubprocessRunner()  # tests swap in a recorder

    def _merges(self) -> merge_http.MergeApi | None:
        """Return the merge service the backend carries (`merge_service`), None when it has none."""
        api = getattr(self.backend, "merge_service", None)
        return api if isinstance(api, merge_http.MergeApi) else None

    def _merge_get(self, path: str) -> Callable[[], Reply] | None:
        """Return the GET /api/merges handler when the backend has a merge service."""
        api = self._merges()
        if path != merge_http.GET_PATH or api is None:
            return None
        return lambda: json_reply(api.suggestions())

    def get(self, target: str, last_event_id: str | None = None, *, local: bool = False) -> Reply | SseReply:
        """Answer a GET: API route, SSE feed or static file; `local` is the gate's verdict on the Host."""
        parts = urlsplit(target)
        path = parts.path
        if path == "/api/live":
            return _guard(lambda: self._live(parse_qs(parts.query), _last_seq(last_event_id)))
        handler = self._simple.get(path) or self._merge_get(path) or getroutes.route(path, self.backend)
        if handler is not None:
            return _guard(handler)
        if path == tokens_api.PREFIX or path.startswith(tokens_api.PREFIX + "/"):
            return _guard(lambda: self._tokens(path, parts.query))
        if (reply := self._task_route(path)) is not None:
            return reply
        if not path.startswith("/api/") and (static := self.site.serve(path, local=local)) is not None:
            return static
        return error_reply("not_found", "no such route")

    def _task_route(self, path: str) -> Reply | SseReply | None:
        """Answer /api/task/<id> and its screenshots; None when path is neither."""
        if match := SHOT_PATH.fullmatch(path):
            return _guard(partial(self._shot, *match.groups()))
        if match := issues.PATH.fullmatch(path):
            return _guard(partial(issues.reply, self.backend, match.group(1)))
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
        snapshot = {"type": "stage", **{key: detail["card"][key] for key in SNAPSHOT_KEYS}}
        return SseReply(snapshot, self.backend.subscribe(ids[0]), last_seq, self.backend.floor(ids[0]))

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
        path = urlsplit(target).path
        cap = newtask.MAX_BODY if newtask.big(path) else MAX_BODY
        if size < 0 or size > cap:
            return error_reply(
                "bad_request", f"request body too large (over {cap // 1024} KB) or bad length", close=True
            )
        raw = read(size) if size else b""
        if (why := check_post(origin, token, expected=self.token, origins=self.origins)) is not None:
            return error_reply("forbidden", why)
        found = merge_http.POST_PATH.fullmatch(path)
        if path == newtask.PATH:  # create, then the card's own Start click through _action
            reply = _guard(
                lambda: newtask.handle(self.backend, raw, lambda card: _guard(partial(self.start_card, card)))
            )
        elif path == settings.PATH:
            reply = _guard(lambda: settings.handle(self.backend, raw))
        elif found and (api := self._merges()) is not None:
            reply = _guard(lambda: merge_http.handle_post(api, found, raw))
        elif (hit := asks_http.POST_PATH.fullmatch(path)) and (ask := asks_http.api_of(self.backend)):
            reply = _guard(lambda: asks_http.handle_post(ask, hit, raw))
        elif mutation := sessions_http.POST_PATH.fullmatch(path):
            reply = _guard(lambda: sessions_http.handle_post(self, mutation, raw))
        else:
            reply = _guard(lambda: self._action(path, raw))
        return reply

    def start_card(self, card: str) -> Reply:  # noqa: D102 - the card's own Start click
        return self._action(f"/api/task/{card}/start", b"")

    def _request(self, path: str, raw: bytes) -> tuple[str, str, dict[str, Any]] | Reply:
        """Resolve route, task id and body into (id8, action, body), or the refusal to send."""
        match = ACTION_PATH.fullmatch(path)
        if match is None or match.group(2) not in bodies.ACTIONS:
            return error_reply("not_found", "no such route")
        id8, action = match.groups()
        if not CARD_ID.fullmatch(id8):
            return error_reply("bad_request", "task id must look like abcd1234-0")
        body = bodies.parse(raw)
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
        card = detail["card"]
        offered = next((a for a in card["actions"] if a["id"] == action), None)
        if action == "start" and offered is None and card["auto_start"] is not None:
            return json_reply({"ok": True, "task": card})  # the click lost the race to the auto-start
        if offered is None or not offered["enabled"]:
            reason = offered["reason"] if offered else None
            return error_reply("disabled", reason or "action not available")
        if body.get("auto_ship") is True and not (option := offered.get("option") or {}).get("enabled"):
            return error_reply("disabled", option.get("reason") or "Auto-ship is not offered here")
        self._invoke(action, id8, body)
        fresh = self.backend.task(id8) or detail
        return json_reply({"ok": True, "task": fresh["card"]})

    def _invoke(self, action: str, id8: str, body: dict[str, Any]) -> None:
        backend = self.backend
        match action:
            case "start":
                backend.start(id8, auto_ship=body.get("auto_ship"))
            case "spec-answers":
                backend.spec_answers(id8, body["answers"])
            case "send":
                backend.send(id8, body["text"], bodies.images(body))
            case "lesson-approve":
                backend.lesson_approve(id8, body["lesson_id"])
            case _:  # an id-only click, or `model` with its one keyword (bodies.check pins the body)
                getattr(backend, action.replace("-", "_"))(id8, **body)
