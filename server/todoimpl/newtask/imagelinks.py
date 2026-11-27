"""A note's images as the board shows them (T2535): found in the note text, stripped from titles, read safely.

A note links an image by its dufs URL (`images.URL/<folder>/<file>`) or, written by the board for a
session, by its local path (`<images.root()>/<folder>/<file>`). Both name the same file. `read` serves one
to the page or the app: the names must match the dufs link's character classes, the resolved file must stay
inside the root, and the first bytes must prove an image.
"""

from __future__ import annotations

import functools
import re
from typing import TYPE_CHECKING, Any

from . import images, noteimages

if TYPE_CHECKING:
    from pathlib import Path

FOLDER = re.compile(r"[A-Za-z0-9_-]+")
FILE = re.compile(r"[A-Za-z0-9_-]+\.[a-z0-9]{1,10}")
TYPES = {
    "png": "image/png",
    "jpeg": "image/jpeg",
    "jpg": "image/jpeg",
    "webp": "image/webp",
    "gif": "image/gif",
}
MAX_BYTES = 20 * 1024 * 1024  # a phone photo is a few MB; anything far bigger is no note image


class ImageLinkError(ValueError):
    """Why an image cannot be served (bad name, outside the root, missing, not an image)."""


@functools.lru_cache(maxsize=8)  # every card of every board build asks
def _pattern(root: Path) -> re.Pattern[str]:
    bases = "|".join(re.escape(b) for b in (images.URL, str(root)))
    return re.compile(rf"(?:{bases})/({FOLDER.pattern})/({FILE.pattern})(?![A-Za-z0-9])")


def links(text: str, root: Path) -> list[dict[str, str]]:
    """Return the images `text` links, first-seen order, each once: `{folder, file}`."""
    found: list[dict[str, str]] = []
    for folder, file in _pattern(root).findall(text):
        if (one := {"folder": folder, "file": file}) not in found:
            found.append(one)
    return found


def card_fields(title: str, body: str) -> dict[str, Any]:
    """Return the card's `images` and stripped `title` (only an image: its file name), {} with no image."""
    root = images.root()
    found = links(f"{title}\n{body}", root)
    return {"images": found, "title": strip_title(title, root) or found[0]["file"]} if found else {}


def strip_title(title: str, root: Path) -> str:
    """Return the title without its image markdown (`![alt](<image link>)`); may be empty."""
    return " ".join(_markdown(root).sub(" ", title).split())


@functools.lru_cache(maxsize=8)
def _markdown(root: Path) -> re.Pattern[str]:
    return re.compile(rf"!\[[^\]]*\]\(\s*{_pattern(root).pattern}\s*\)")


def read(root: Path, folder: str, file: str) -> tuple[bytes, str]:
    """Return (bytes, content type) of one note image; raise `ImageLinkError` saying why not."""
    if not FOLDER.fullmatch(folder) or not FILE.fullmatch(file) or file.startswith("."):
        msg = "bad image name"
        raise ImageLinkError(msg)
    base = root.resolve()
    path = (root / folder / file).resolve()
    if not path.is_relative_to(base):
        msg = "image is outside the images folder"
        raise ImageLinkError(msg)
    try:
        with path.open("rb") as handle:
            data = handle.read(MAX_BYTES + 1)
    except OSError as exc:
        msg = "no such image"
        raise ImageLinkError(msg) from exc
    found = noteimages.kind(data[:16])
    if found is None or len(data) > MAX_BYTES:
        msg = "not an image (png, jpeg, webp, gif) or too big"
        raise ImageLinkError(msg)
    return data, TYPES[found]
