"""The relay's kind allowlist: each kind names the HTTP route it stands for.

A routed kind is turned into the exact GET or POST the page would send and answered by the same Router, so a
relay request passes every check a click passes (guard 4). The table is the only way from a kind to code:
there is no lookup by a name taken from the request (guard 1).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final, Literal
from urllib.parse import quote

from todoimpl.http import bodies, newtask, settings
from todoimpl.http import sessions as sessions_http
from todoimpl.tokens_api import router as tokens_api

if TYPE_CHECKING:
    from collections.abc import Callable

type Lane = Literal["act", "read"]
ASK_VERBS: Final = ("answer", "take-recommended", "run", "undo", "approve", "reject")
SESSION_VERBS: Final = ("resume", "mark", "delete", "handoff")
LOCAL: Final = ("live_watch", "snapshot_refresh", "notify_test", "image_upload")  # answered by the worker


@dataclass(frozen=True)
class Call:
    """One HTTP request for the Router: a GET target, or a POST path with its raw body."""

    method: Literal["GET", "POST"]
    target: str
    raw: bytes = b""


@dataclass(frozen=True)
class Kind:
    """A routed kind: its lane and how a (validated) body becomes the Call."""

    lane: Lane
    call: Callable[[dict[str, Any]], Call]


def _json(value: object) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()


def _seg(text: str) -> str:
    """One path segment; nothing in it can end the path or start a query."""
    return quote(str(text), safe="")


def _task(action: str) -> Kind:
    return Kind("act", lambda b: Call("POST", f"/api/task/{_seg(b['card'])}/{action}", _json(b["args"])))


def _ask(verb: str) -> Kind:
    return Kind("act", lambda b: Call("POST", f"/api/task/{_seg(b['card'])}/ask/{verb}", _json(b["args"])))


def _merge(verb: str) -> Kind:
    return Kind("act", lambda b: Call("POST", f"/api/merge/{_seg(b['group'])}/{verb}", _json(b["args"])))


def _session(verb: str) -> Kind:
    return Kind("act", lambda b: Call("POST", f"{sessions_http.GET_PATH}/{verb}", _json(b["args"])))


def _args(path: str) -> Kind:
    return Kind("act", lambda b: Call("POST", path, _json(b["args"])))


def _tokens(body: dict[str, Any]) -> Call:
    query = f"?{body['query']}" if body["query"] else ""
    return Call("GET", f"{tokens_api.PREFIX}{body['path']}{query}")


READS: Final[dict[str, Kind]] = {
    "task_detail": Kind("read", lambda b: Call("GET", f"/api/task/{_seg(b['card'])}")),
    "task_issues": Kind("read", lambda b: Call("GET", f"/api/task/{_seg(b['card'])}/issues")),
    "task_shot": Kind("read", lambda b: Call("GET", f"/api/task/{_seg(b['card'])}/shot/{b['name']}")),
    "umbrella": Kind("read", lambda b: Call("GET", f"/api/umbrella/{_seg(b['card'])}")),
    "umbrella_log": Kind(
        "read", lambda b: Call("GET", f"/api/umbrella/{_seg(b['card'])}/log/{_seg(b['log'])}")
    ),
    "tokens": Kind("read", _tokens),
    "image_get": Kind(
        "read", lambda b: Call("GET", f"/api/image/{_seg(b['folder'])}/{_seg(b['file'])}")
    ),  # T2535
}
ROUTED: Final[dict[str, Kind]] = {
    **{f"task_{a.replace('-', '_')}": _task(a) for a in bodies.ACTIONS},
    **{f"ask_{v.replace('-', '_')}": _ask(v) for v in ASK_VERBS},
    "new_task": _args(newtask.PATH),
    "credits_fallback": _args(settings.PATH),
    **{f"merge_{v}": _merge(v) for v in ("merge", "dismiss")},
    **{f"session_{v}": _session(v) for v in SESSION_VERBS},
    **READS,
}
ALL: Final = (*ROUTED, *LOCAL)


def lane_of(kind: str) -> Lane:
    """Return the lane a kind runs in: writes one at a time, reads up to four at once."""
    found = ROUTED.get(kind)
    return found.lane if found is not None else "read"
