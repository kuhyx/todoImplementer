"""Run a kind's Call through the Router and turn the Reply into a relay result (or a refusal).

The Router is the one the page talks to, called with its own token and loopback Origin: a relay request passes
the same POST checks, body checks and "offered and enabled" rule as a click (guard 4).
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any, Final

from rtdb_relay.server import RequestError

from todoimpl.http.reply import STATUS
from todoimpl.http.routes import SseReply

if TYPE_CHECKING:
    from todoimpl.http.reply import Reply
    from todoimpl.http.routes import Router

    from .kinds import Call

MAX_RESULT: Final = 4 * 1024 * 1024  # guard 7: results over 4 MB are too_large
RETRY: Final = frozenset({"internal", "upstream_unavailable", "conflict"})
CODE_OF: Final = {status: code for code, status in reversed(STATUS.items())}


def send(router: Router, call: Call) -> Reply:
    """Answer one Call with the Router (blocking: run it in a thread)."""
    if call.method == "GET":
        reply = router.get(call.target, local=True)
        if isinstance(reply, SseReply):  # only /api/live streams, and no kind maps to it
            msg = "stream routes are not relayed"
            raise RequestError(code="internal", message=msg)
        return reply
    raw = call.raw
    return router.post(call.target, router.origins[-1], router.token, str(len(raw)), lambda n: raw[:n])


def refusal(reply: Reply) -> RequestError:
    """Return the Reply's contract error, or one named after its status when the body has none."""
    code, message = CODE_OF.get(reply.status, "internal"), f"HTTP {reply.status}"
    try:
        error = json.loads(reply.body).get("error")
    except ValueError, AttributeError:
        error = None
    if isinstance(error, dict) and isinstance(error.get("code"), str):
        code, message = error["code"], str(error.get("message") or message)
    elif isinstance(error, str):
        message = error
    return RequestError(code, message, retry=code in RETRY)


def data_of(reply: Reply) -> dict[str, Any]:
    """Return the result data of a 200 Reply: its JSON object without `ok`, PNG as base64, text as {text}."""
    if reply.status != 200:  # noqa: PLR2004 - HTTP OK
        raise refusal(reply)
    if reply.ctype == "image/png":
        data: dict[str, Any] = {"png_b64": base64.b64encode(reply.body).decode()}
    elif reply.ctype.startswith("image/"):  # a note image (T2535): any of png, jpeg, webp, gif
        data = {"data_b64": base64.b64encode(reply.body).decode(), "type": reply.ctype}
    elif reply.ctype.startswith("application/json"):
        body = json.loads(reply.body)
        data = {k: v for k, v in body.items() if k != "ok"} if isinstance(body, dict) else {"data": body}
    else:
        data = {"text": reply.body.decode("utf-8", "replace")}
    if len(json.dumps(data, separators=(",", ":"))) > MAX_RESULT:
        msg = "the answer is over 4 MB"
        raise RequestError(code="too_large", message=msg)
    return data
