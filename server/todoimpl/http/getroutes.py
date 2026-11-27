"""GET routes that live in their own modules: the umbrella track (`umbrella.py`) and note images (T2535)."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.newtask import imagelinks, images

from . import umbrella
from .reply import Reply, error_reply

if TYPE_CHECKING:
    from collections.abc import Callable

    from .umbrella import Backend

IMAGE_PATH = re.compile(r"/api/image/(.*)")
MAX_AGE = (("Cache-Control", "private, max-age=86400"),)  # a dufs image never changes under its name


def route(path: str, backend: Backend) -> Callable[[], Reply] | None:
    """Return the handler for an umbrella or image path, None when the path is neither."""
    if match := IMAGE_PATH.fullmatch(path):
        return lambda: image(match.group(1))
    return umbrella.route(path, backend)


def image(rest: str) -> Reply:
    """Answer one note image's bytes: 400 for a bad name or path, 404 when it is no image here."""
    folder, _, file = rest.partition("/")  # a third segment stays in `file` and fails its name check
    try:
        data, ctype = imagelinks.read(images.root(), folder, file)
    except imagelinks.ImageLinkError as exc:
        code = "bad_request" if "name" in str(exc) or "outside" in str(exc) else "not_found"
        return error_reply(code, str(exc))
    return Reply(200, data, ctype, MAX_AGE)
