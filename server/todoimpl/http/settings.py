"""POST /api/settings/credits-fallback: the one global setting (not task-scoped, so not in ACTION_PATH)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from .backend import Backend

PATH = "/api/settings/credits-fallback"


def handle(backend: Backend, raw: bytes) -> Reply:
    """Validate `{enabled: bool}` (contracts/requests.schema.json credits_fallback) and store it."""
    try:
        body = json.loads(raw) if raw else {}
    except ValueError:
        return error_reply("bad_request", "body is not valid JSON")
    if not isinstance(body, dict) or set(body) != {"enabled"} or not isinstance(body["enabled"], bool):
        return error_reply("bad_request", "body must be exactly {enabled: true or false}")
    return json_reply({"ok": True, "credits": backend.set_credits_fallback(enabled=body["enabled"])})
