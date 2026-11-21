"""POST /api/peer/{send,await,inbox,reply}: sessions on this PC message each other (DOCS-peer.md).

Loopback only (the Host is the bound 127.0.0.1 origin and nothing forwarded it) and gated by the peer token
from `$TODOIMPL_HOME/peer.token` in `X-Todoimpl-Peer-Token`, never by the browser's CSRF token: a request
with an Origin header (a browser) is refused. Every caller names itself with `label` (and its `sender` id
from an earlier answer), or a board session with `card` and `card_key`.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.peer import limits
from todoimpl.peer.limits import Refusal

from .reply import STATUS, Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

    from todoimpl.peer.senders import Sender

PREFIX = "/api/peer/"
TOKEN_HEADER = "X-Todoimpl-Peer-Token"
MAX_BODY = 64 * 1024  # an 8 KB text, escaped, plus the fields


class Headers(Protocol):  # noqa: D101 - the slice of http.client.HTTPMessage used here
    def get(self, name: str, default: None = None) -> str | None: ...  # noqa: D102


class PeerHub(Protocol):  # noqa: D101 - what the endpoint needs of todoimpl.peer.hub.Hub
    def token_ok(self, given: str | None) -> bool: ...  # noqa: D102
    def identify(  # noqa: D102
        self, label: str | None = None, sender: str | None = None, card: str | None = None, card_key: str | None = None
    ) -> Sender: ...
    def send(self, who: Sender, to: str, text: str, reply_to: str | None = None) -> dict[str, Any]: ...  # noqa: D102
    def reply(self, who: Sender, msg_id: str, text: str) -> dict[str, Any]: ...  # noqa: D102
    def wait(self, msg_id: str, timeout: float) -> dict[str, Any]: ...  # noqa: D102
    def inbox(self, who: Sender, wait: float) -> list[dict[str, Any]]: ...  # noqa: D102


def owns(path: str) -> bool:
    """Whether this module answers `path`."""
    return path.startswith(PREFIX)


def _refused(exc: Refusal) -> Reply:
    body: dict[str, Any] = {"ok": False, "error": {"code": exc.code, "message": exc.message}}
    if exc.retry_after is not None:
        body["retry_after"] = round(exc.retry_after, 3)
    return json_reply(body, STATUS[exc.code])


def _text(body: dict[str, Any], key: str, *, optional: bool = False) -> str | None:
    value = body.get(key)
    if value is None and optional:
        return None
    if not isinstance(value, str):
        msg = f"{key} must be a string"
        raise Refusal(msg)
    return value


def _seconds(body: dict[str, Any], key: str, default: float) -> float:
    value = body.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        msg = f"{key} must be a number of seconds"
        raise Refusal(msg)
    return min(max(float(value), 0.0), limits.AWAIT_SLICE)


def _dispatch(hub: PeerHub, route: str, body: dict[str, Any]) -> dict[str, Any]:
    who = hub.identify(
        _text(body, "label", optional=True),
        _text(body, "sender", optional=True),
        _text(body, "card", optional=True),
        _text(body, "card_key", optional=True),
    )
    actions: dict[str, Callable[[], dict[str, Any]]] = {
        "send": lambda: {"message": hub.send(
            who, str(_text(body, "to")), str(_text(body, "text")), _text(body, "reply_to", optional=True))},
        "reply": lambda: {"message": hub.reply(who, str(_text(body, "id")), str(_text(body, "text")))},
        "await": lambda: {"message": hub.wait(str(_text(body, "id")), _seconds(body, "timeout", limits.AWAIT_SLICE))},
        "inbox": lambda: {"messages": hub.inbox(who, _seconds(body, "wait", 0.0))},
    }  # fmt: skip
    return {"ok": True, "sender": who.id, "as": who.display, **actions[route]()}


def handle(  # noqa: PLR0911 - one refusal per gate
    hub: PeerHub | None, path: str, *, local: bool, headers: Headers, read: Callable[[int], bytes]
) -> Reply:
    """Answer one peer POST."""
    route = path.removeprefix(PREFIX)
    if hub is None or route not in {"send", "reply", "await", "inbox"}:
        return error_reply("not_found", "no such route")
    try:
        size = int(headers.get("Content-Length") or 0)
    except ValueError:
        size = -1
    if not 0 <= size <= MAX_BODY:
        return error_reply("bad_request", f"request body too large (over {MAX_BODY // 1024} KB)", close=True)
    raw = read(size) if size else b""
    if not local or headers.get("X-Forwarded-For") is not None:
        return error_reply("forbidden", "peer messages are loopback only")
    if headers.get("Origin") is not None:
        return error_reply("forbidden", "browser requests are refused here")
    if not hub.token_ok(headers.get(TOKEN_HEADER)):
        return error_reply("forbidden", "bad peer token")
    try:
        body = json.loads(raw or b"{}")
    except ValueError:
        body = None
    if not isinstance(body, dict):
        return error_reply("bad_request", "the body must be a JSON object")
    try:
        return json_reply(_dispatch(hub, route, body))
    except Refusal as exc:
        return _refused(exc)
