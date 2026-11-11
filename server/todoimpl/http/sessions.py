"""GET /api/sessions and POST /api/sessions/<resume|mark|delete> (contracts/sessions.schema.json).

The POSTs run after the same Origin + CSRF check as Ship (`Router.post`): this server is reachable through
Caddy and Google sign-in, and a resume opens a terminal on the desktop. Mutation outcomes, refusals
included, are HTTP 200 with the `result` shape; only bad JSON is a 400.
"""

from __future__ import annotations

import json
import re
from typing import TYPE_CHECKING

from todoimpl.sessions import api, router

from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner

GET_PATH = "/api/sessions"
POST_PATH = re.compile(r"/api/sessions/(resume|mark|delete)")


def listing() -> Reply:
    """Serve the scanned list of manual sessions."""
    return json_reply(api.listing())


def handle_post(runner: CommandRunner, found: re.Match[str], raw: bytes) -> Reply:
    """Run the mutation the path names on the JSON body (an empty body is `{}`)."""
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        return error_reply("bad_request", "body is not valid JSON")
    payload = router.mutate(runner, found.group(1), body)
    assert payload is not None  # noqa: S101 - POST_PATH only matches the three known names
    return json_reply(payload)
