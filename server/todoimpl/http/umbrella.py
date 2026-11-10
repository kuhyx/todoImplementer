"""GET /api/umbrella/<id> (the tracking view) and /api/umbrella/<id>/log/<child id> (a worker log tail)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

    from .backend import Backend

PATH = re.compile(r"/api/umbrella/([^/]+)(?:/log/([^/]+))?")
CARD_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")


def route(path: str, backend: Backend) -> Callable[[], Reply] | None:
    """Return the handler for an umbrella path, None when the path is not one."""
    match = PATH.fullmatch(path)
    if match is None:
        return None
    return lambda: reply(backend, *match.groups())


def reply(backend: Backend, id8: str, child: str | None) -> Reply:
    """Answer the track object, or (with a child id) the tail of its newest worker log."""
    if not CARD_ID.fullmatch(id8) or (child is not None and not CARD_ID.fullmatch(child)):
        return error_reply("bad_request", "ids must look like abcd1234-0")
    if child is None:
        found = backend.umbrella(id8)
        return json_reply(found) if found is not None else error_reply("not_found", "no umbrella run")
    text = backend.worker_log(id8, child)
    if text is None:
        return error_reply("not_found", "no worker log")
    return Reply(200, text.encode(), "text/plain; charset=utf-8", (("Cache-Control", "no-store"),))
