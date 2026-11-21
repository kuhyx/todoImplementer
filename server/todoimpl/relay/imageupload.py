"""The `image_upload` relay kind (T2426): one image from the app, staged like `POST /api/upload`.

The relay seals each request into one RTDB string (10 MB cap), so a task's images used to share one request
and its budget: at most 8. Now the app sends each image alone first and the task names the staged ids
(`{upload: <id>}`, the page's way), so a task takes any number of images (kuhy, 2026-11-21).
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import io
from typing import Any

from rtdb_relay.server import RequestError

from todoimpl.newtask import noteimages, uploads


def _stage(data: bytes) -> dict[str, Any]:
    ext = noteimages.kind(data[:16])
    if ext is None:
        raise RequestError(code="bad_request", message="not a png, jpeg, webp or gif image")
    if len(data) > noteimages.MAX_INLINE:
        raise RequestError(code="bad_request", message=f"image over {noteimages.MAX_INLINE // uploads.MB} MB")
    # A stream: each 64 KiB read continues where the last stopped (T2446: `data[:n]` restarted each one).
    staged = uploads.stage(io.BytesIO(data).read, len(data), f"image.{ext}", uploads.root())
    return {"data": {"upload": {"id": staged.id, "name": staged.name, "size": staged.size}}}


async def handle(body: dict[str, Any]) -> dict[str, Any]:
    """Decode `data_b64` and stage it; answer `{upload: {id, name, size}}` as the upload route does."""
    try:
        data = base64.b64decode(str(body.get("data_b64", "")), validate=True)
    except binascii.Error, ValueError:
        raise RequestError(code="bad_request", message="data_b64 is no base64") from None
    return await asyncio.to_thread(_stage, data)
