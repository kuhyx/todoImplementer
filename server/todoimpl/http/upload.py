"""POST /api/upload: one new-task attachment, streamed to the staging dir before the new-task POST claims it.

The body is the raw file (any type), its name percent-encoded in `X-Todoimpl-Name`. Origin and token are
checked before a byte is read, and a file over the cap is refused from its Content-Length alone. Answer:
response.schema.json `{ok, upload: {id, name, size}}`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from todoimpl.newtask import uploads

from .auth import check_post
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

PATH = "/api/upload"
NAME_HEADER = "X-Todoimpl-Name"


class Headers(Protocol):
    """The request headers (http.client's Message, or a dict in tests)."""

    def get(self, name: str, /) -> str | None:
        """Return the header's value, None when it is absent."""
        ...


def handle(expected: str, origins: tuple[str, ...], headers: Headers, read: Callable[[int], bytes]) -> Reply:
    """Stage the body as one file and answer its id; every refusal closes the connection unread."""
    why = check_post(
        headers.get("Origin"), headers.get("X-Todoimpl-Token"), expected=expected, origins=origins
    )
    if why is not None:
        return error_reply("forbidden", why, close=True)
    try:
        size = int(headers.get("Content-Length") or "")
    except ValueError:
        size = -1
    if size < 0:
        return error_reply("bad_request", "bad Content-Length", close=True)
    name = uploads.clean_name(headers.get(NAME_HEADER))
    if size > uploads.MAX_FILE:
        return error_reply("bad_request", f"{name} is over {uploads.MAX_FILE // uploads.MB} MB", close=True)
    try:
        staged = uploads.stage(read, size, name, uploads.root())
    except uploads.ShortBodyError:
        return error_reply("bad_request", f"{name} arrived cut short", close=True)
    except OSError:  # a full disk, or the socket timed out mid-file
        return error_reply("internal", f"{name} could not be stored", close=True)
    return json_reply({"ok": True, "upload": {"id": staged.id, "name": staged.name, "size": staged.size}})
