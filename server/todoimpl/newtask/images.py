"""The todo app's images on kuhy's dufs: where they live here, how notes link them, how a session reads them.

A note links an image as `![](https://kuhy-cloud.duckdns.org/todo-images/<folder>/<file>.<ext>)`; the same
file is `<root>/<folder>/<file>.<ext>` on this PC (root: `$TODOIMPL_IMAGES_ROOT`, default
`~/data/cloud/todo-images`). A headless session cannot log in to dufs, so its prompt carries the local path.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

URL = "https://kuhy-cloud.duckdns.org/todo-images"
LINK = re.compile(re.escape(URL) + r"/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+\.[a-z0-9]{1,10})(?![A-Za-z0-9])")
JPEG_MAGIC = b"\xff\xd8\xff"


def root(env: Mapping[str, str] | None = None) -> Path:
    """Return the local folder behind the dufs `todo-images` URL."""
    env = os.environ if env is None else env
    if found := env.get("TODOIMPL_IMAGES_ROOT"):
        return Path(found)
    return Path(env.get("HOME") or Path.home()) / "data" / "cloud" / "todo-images"


def is_jpeg(data: bytes) -> bool:
    """Tell whether the bytes start like a JPEG file (SOI marker plus the next marker's 0xff)."""
    return data.startswith(JPEG_MAGIC)


def save(images: Sequence[bytes], base: Path, folder: str) -> tuple[str, ...]:
    """Write the images as `<base>/<folder>/<n>.jpg` (n from 1) and return their dufs links."""
    links = []
    for number, data in enumerate(images, 1):
        atomic.write_bytes(base / folder / f"{number}.jpg", data)
        links.append(f"{URL}/{folder}/{number}.jpg")
    return tuple(links)


def localize(text: str, base: Path) -> tuple[str, tuple[Path, ...]]:
    """Rewrite every dufs image link in `text` to its path under `base`; also return those paths in order."""
    found: list[Path] = []

    def local(match: re.Match[str]) -> str:
        path = base / match.group(1) / match.group(2)
        found.append(path)
        return str(path)

    return LINK.sub(local, text), tuple(found)


def session_dirs() -> tuple[Path, ...]:
    """Return the images root as an extra directory a turn may read, when it exists on this PC."""
    found = root()
    return (found,) if found.is_dir() else ()
