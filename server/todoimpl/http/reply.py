"""Transport-neutral replies built by the routes and written by the handler."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

JSON_TYPE = "application/json; charset=utf-8"
STATUS = {
    "bad_request": 400,
    "forbidden": 403,
    "not_found": 404,
    "disabled": 409,
    "conflict": 409,
    "internal": 500,
    "upstream_unavailable": 502,
}


@dataclass(frozen=True)
class Reply:
    """One complete HTTP answer; close asks the handler to drop the connection afterwards."""

    status: int
    body: bytes
    ctype: str = JSON_TYPE
    headers: tuple[tuple[str, str], ...] = ()
    close: bool = False


def json_reply(obj: Any, status: int = 200) -> Reply:  # noqa: ANN401 - any JSON value
    """Encode obj as an uncached JSON answer."""
    body = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode()
    return Reply(status, body, headers=(("Cache-Control", "no-store"),))


def error_reply(code: str, message: str, *, close: bool = False) -> Reply:
    """Build the contract's {ok: false, error: {code, message}} answer with the code's HTTP status."""
    reply = json_reply({"ok": False, "error": {"code": code, "message": message}}, STATUS[code])
    return Reply(reply.status, reply.body, reply.ctype, reply.headers, close)
