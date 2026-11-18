"""POST /api/new-task: kuhy's own task for a repo, with images, then that repo card's own Start click.

Request: contracts/requests.schema.json `new_task`; answer: response.schema.json (`note`, `started`, `task`).
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from http import HTTPStatus
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from todoimpl.newtask.images import is_jpeg

from .bodies import MAX_TEXT, parse
from .reply import Reply, error_reply, json_reply

if TYPE_CHECKING:
    from collections.abc import Callable

    from .backend import Backend

PATH = "/api/new-task"
MB = 1024 * 1024
MAX_BODY = 40 * MB  # 8 images of up to 6 MB each, base64 (4/3), plus the text
MAX_IMAGES = 8
MAX_IMAGE = 6 * MB
MAX_TITLE = 200
REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
KEYS = frozenset({"repo", "title", "body", "images", "files"})
FILE_ID = re.compile(r"[0-9a-f]{32}")
MAX_FILES = 1000  # ids only; the real cap is uploads.MAX_TASK bytes


@dataclass(frozen=True)
class NewTask:
    """A checked request: title and body stripped, images decoded JPEG bytes, files staged upload ids."""

    repo: str
    title: str
    body: str
    images: tuple[bytes, ...]
    files: tuple[str, ...] = ()


@runtime_checkable
class NewTaskApi(Protocol):
    """What the route needs from the service; its refusals are BackendError."""

    def create(self, task: NewTask) -> tuple[str, str]:
        """Add the task; return (note id8, the card id that now holds it)."""
        ...


def _image(number: int, item: object) -> bytes | str:
    data = item.get("data_b64") if isinstance(item, dict) and set(item) == {"data_b64"} else None
    if not isinstance(data, str):
        return f"image {number} must be exactly {{data_b64}}"
    try:
        blob = base64.b64decode(data, validate=True)
    except binascii.Error:
        return f"image {number} is not base64"
    if len(blob) > MAX_IMAGE:
        return f"image {number} is over {MAX_IMAGE // MB} MB"
    return blob if is_jpeg(blob) else f"image {number} is not a JPEG"


def _images(raw: object) -> tuple[bytes, ...] | str:
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        return f"images must be a list of at most {MAX_IMAGES}"
    out: list[bytes] = []
    for number, item in enumerate(raw, 1):
        blob = _image(number, item)
        if isinstance(blob, str):
            return blob
        out.append(blob)
    return tuple(out)


def _files(raw: object) -> tuple[str, ...] | str:
    if not isinstance(raw, list) or len(raw) > MAX_FILES:
        return f"files must be at most {MAX_FILES} distinct upload ids"
    ids = tuple(i for i in raw if isinstance(i, str) and FILE_ID.fullmatch(i))
    return ids if len(ids) == len(raw) == len(set(ids)) else _files(None)


def _attachments(body: dict[str, Any]) -> tuple[tuple[bytes, ...], tuple[str, ...]] | str:
    images = _images(body.get("images", []))
    files = _files(body.get("files", []))
    if isinstance(images, str) or isinstance(files, str):
        return images if isinstance(images, str) else str(files)
    return images, files


def _title(title: object) -> str | None:
    ok = (
        isinstance(title, str) and title.strip() and len(title) <= MAX_TITLE and not {"\n", "\r"} & set(title)
    )
    return title.strip() if ok and isinstance(title, str) else None


def check(raw: bytes) -> NewTask | str:
    """Return the checked request, or what is wrong with it."""
    body: dict[str, Any] | str = parse(raw)
    if isinstance(body, str):
        return body
    if not {"repo", "title"} <= set(body) <= KEYS:
        return "body must be {repo, title, body?, images?, files?}"
    repo, text = body["repo"], body.get("body", "")
    if not isinstance(repo, str) or not REPO.fullmatch(repo):
        return "repo must look like owner/name"
    if (title := _title(body["title"])) is None:
        return f"title must be 1..{MAX_TITLE} characters on one line"
    if not isinstance(text, str) or len(text) > MAX_TEXT:
        return f"body must be text of at most {MAX_TEXT} characters"
    attached = _attachments(body)
    return attached if isinstance(attached, str) else NewTask(repo, title, text.strip(), *attached)


def handle(backend: Backend, raw: bytes, start: Callable[[str], Reply]) -> Reply:
    """Create the task, then press the card's Start (it refuses on a card already at work: still ok)."""
    api = getattr(backend, "new_task_service", None)
    if not isinstance(api, NewTaskApi):
        return error_reply("not_found", "no such route")
    task = check(raw)
    if isinstance(task, str):
        return error_reply("bad_request", task)
    note, card = api.create(task)
    started = start(card)
    if started.status == HTTPStatus.OK:
        return json_reply(
            {"ok": True, "note": note, "started": True, "task": json.loads(started.body)["task"]}
        )
    detail = backend.task(card)
    if detail is None:
        return error_reply("not_found", f"note {note} got the task, but card {card} is not on the board yet")
    return json_reply({"ok": True, "note": note, "started": False, "task": detail["card"]})
