"""GET /api/task/<id>/issues: the raw free-issues.jsonl of a task (umbrella/issues.py)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .reply import Reply, error_reply

if TYPE_CHECKING:
    from .backend import Backend

PATH = re.compile(r"/api/task/([^/]+)/issues")
CARD_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")


def reply(backend: Backend, id8: str) -> Reply:
    """Answer with the raw log (empty when nothing went wrong); 404 for an unknown task."""
    if not CARD_ID.fullmatch(id8):
        return error_reply("bad_request", "task id must look like abcd1234-0")
    text = backend.issues(id8)
    if text is None:
        return error_reply("not_found", "unknown task")
    return Reply(200, text.encode(), "application/x-ndjson", (("Cache-Control", "no-store"),))
