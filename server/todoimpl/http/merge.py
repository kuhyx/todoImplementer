"""GET /api/merges and POST /api/merge/<group>/<merge|dismiss> (contracts/merge.schema.json)."""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

GET_PATH = "/api/merges"
POST_PATH = re.compile(r"/api/merge/([0-9a-f]{12})/(merge|dismiss)")


@runtime_checkable
class MergeApi(Protocol):
    """What the routes need from the merge service; its refusals are BackendError."""

    def suggestions(self) -> dict[str, Any]:
        """GET body."""
        ...

    def merge(self, group_id: str) -> dict[str, Any]:
        """Merge click; the POST answer."""
        ...

    def dismiss(self, group_id: str) -> dict[str, Any]:
        """Dismiss click; the POST answer."""
        ...


def handle_post(api: MergeApi, found: re.Match[str], raw: bytes) -> Reply:
    """Run the click named by the path; the body must be empty or `{}`."""
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        return error_reply("bad_request", "body is not valid JSON")
    if body != {}:
        return error_reply("bad_request", "body must be empty")
    group_id, action = found.groups()
    click: Callable[[str], dict[str, Any]] = api.merge if action == "merge" else api.dismiss
    return json_reply(click(group_id))
