"""POST /api/task/<card>/part-edit: edit a part's own title and text before the run reaches it (856c0f0a).

Body `{part, title, body}` (contracts/requests.schema.json `part_edit`). The card's own `parts[].edit`, which
the board computes, decides: a part it does not offer is refused with the reason the page shows. This is a
path of its own on purpose: `ItemView.update_task` still refuses title and body edits through a card.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from . import bodies
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from .backend import Backend

PATH = re.compile(r"/api/task/([A-Za-z0-9]{8}-[0-9]+)/part-edit")
PART_ID = re.compile(r"[A-Za-z0-9]{8}-[0-9]+")
KEYS = frozenset({"part", "title", "body"})
MAX_TITLE = 200


@runtime_checkable
class PartApi(Protocol):
    """What the route needs from the part service; refusals are BackendError."""

    def edit(self, card: str, part: str, title: str, body: str) -> None:
        """Write the part's new title and text into its note."""
        ...


def check(body: dict[str, object]) -> tuple[str, str, str] | str:
    """Return (part, title, body) of a valid request, else what is wrong with it."""
    if set(body) != KEYS:
        return "body must be exactly {part, title, body}"
    part, title, text = body["part"], body["title"], body["body"]
    if not isinstance(part, str) or not PART_ID.fullmatch(part):
        return "part must look like abcd1234-0"
    if not isinstance(title, str) or not title.strip() or len(title) > MAX_TITLE or {"\n", "\r"} & set(title):
        return f"title must be 1..{MAX_TITLE} characters on one line"
    if not isinstance(text, str) or len(text) > bodies.MAX_TEXT:
        return f"body must be text of at most {bodies.MAX_TEXT} characters"
    return part, title.strip(), text


def handle(backend: Backend, card: str, raw: bytes) -> Reply:
    """Edit the part when its card offers that, and answer {ok, task: the fresh card}."""
    api = getattr(backend, "part_service", None)
    if not isinstance(api, PartApi):
        return error_reply("not_found", "no such route")
    body = bodies.parse(raw)
    found = check(body) if isinstance(body, dict) else body
    if isinstance(found, str):
        return error_reply("bad_request", found)
    key, title, text = found
    detail = backend.task(card)
    if detail is None:
        return error_reply("not_found", "unknown task")
    part = next((p for p in detail["card"].get("parts") or () if p["id"] == key), None)
    if part is None:
        return error_reply("not_found", "unknown part")
    if not part["edit"]["enabled"]:
        return error_reply("disabled", part["edit"]["reason"])
    api.edit(card, key, title, text)
    fresh = backend.task(card) or detail
    return json_reply({"ok": True, "task": fresh["card"]})
