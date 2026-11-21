"""Numbered images for Send to Claude and New task: `image_ref` items, read, checked, written, named.

An `image_ref` (contracts/requests.schema.json) is `{upload: <id>}` (staged by POST /api/upload, the page's
way, 10 MB) or `{data_b64}` (inline, the phone's way through the relay, 6 MB). Item N is `[Image #N]` in
kuhy's text. The type comes from the first bytes, never the name: png, jpeg, webp or gif only.
"""

from __future__ import annotations

import base64
import binascii
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from . import uploads

if TYPE_CHECKING:
    from collections.abc import Sequence

MAX_IMAGE = 10 * uploads.MB
MAX_INLINE = 6 * uploads.MB  # 8 of them as base64 fit the 40 MB new-task body
MAX_IMAGES = 1000  # no real cap (kuhy, 2026-11-21): the bytes are capped, uploads.MAX_TASK (T2426)
KINDS = ((b"\x89PNG\r\n\x1a\n", "png"), (b"\xff\xd8\xff", "jpg"), (b"GIF87a", "gif"), (b"GIF89a", "gif"))
NOT_IMAGE = "is not a PNG, JPEG, WebP or GIF"
LEGEND = "(runner) kuhy attached images; open each with the Read tool:"


type Ref = bytes | str  # inline bytes, or a staged upload id


class ImageError(ValueError):
    """A list of image refs the server refuses; the message is what the page shows."""


@dataclass(frozen=True)
class Picture:
    """One checked image: its extension and its bytes (inline) or its staged file."""

    ext: str
    source: bytes | Path


def kind(head: bytes) -> str | None:
    """Return the extension the first bytes prove, or None when they are no png, jpeg, webp or gif."""
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return next((ext for magic, ext in KINDS if head.startswith(magic)), None)


def _ref(number: int, item: object) -> Ref:
    bad = ImageError(f"image {number} must be {{upload}} or {{data_b64}}")
    if not isinstance(item, dict) or len(item) != 1:
        raise bad
    ((key, value),) = item.items()
    if key == "upload" and isinstance(value, str) and uploads.ID.fullmatch(value):
        return value
    if key != "data_b64" or not isinstance(value, str):
        raise bad
    try:
        blob = base64.b64decode(value, validate=True)
    except binascii.Error:
        msg = f"image {number} is not base64"
        raise ImageError(msg) from None
    if len(blob) > MAX_INLINE:
        msg = f"image {number} is over {MAX_INLINE // uploads.MB} MB"
        raise ImageError(msg)
    if kind(blob[:12]) is None:
        msg = f"image {number} {NOT_IMAGE}"
        raise ImageError(msg)
    return blob


def parse(raw: object) -> tuple[Ref, ...]:
    """Return the refs of a body's `images` list in order; raise ImageError on any bad one."""
    if not isinstance(raw, list) or len(raw) > MAX_IMAGES:
        msg = f"images must be a list of at most {MAX_IMAGES}"
        raise ImageError(msg)
    refs: list[Ref] = []
    for number, item in enumerate(raw, 1):
        ref = _ref(number, item)
        if isinstance(ref, str) and ref in refs:
            msg = f"image {number} repeats an upload"
            raise ImageError(msg)
        refs.append(ref)
    return tuple(refs)


def _source(ref: Ref, base: Path) -> tuple[bytes, int, bytes | Path]:
    """Return (first bytes, size, source) of one ref; a staged one must still be there."""
    if isinstance(ref, bytes):
        return ref[:12], len(ref), ref
    staged = uploads.claim((ref,), base)
    if isinstance(staged, str):
        raise ImageError(staged)
    (found,) = staged
    with found.path.open("rb") as file:
        return file.read(12), found.size, found.path


def resolve(refs: Sequence[Ref], base: Path) -> tuple[Picture, ...]:
    """Check every ref by size and first bytes before anything moves; raise ImageError on a bad one."""
    out: list[Picture] = []
    for number, ref in enumerate(refs, 1):
        head, size, source = _source(ref, base)
        if size > MAX_IMAGE:
            msg = f"image {number} is over {MAX_IMAGE // uploads.MB} MB"
            raise ImageError(msg)
        if (ext := kind(head)) is None:
            msg = f"image {number} {NOT_IMAGE}"
            raise ImageError(msg)
        out.append(Picture(ext, source))
    return tuple(out)


def write(pictures: Sequence[Picture], folder: Path, stem: str) -> tuple[Path, ...]:
    """Copy each picture to `<folder>/<stem><N>.<ext>` (N from 1); answer the absolute paths."""
    paths = []
    for number, picture in enumerate(pictures, 1):
        target = (folder / f"{stem}{number}.{picture.ext}").absolute()
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(picture.source, bytes):
            target.write_bytes(picture.source)
        else:
            shutil.copyfile(picture.source, target)
        paths.append(target)
    return tuple(paths)


def release(pictures: Sequence[Picture]) -> None:
    """Drop the staging dirs of the uploads once their copies are in use."""
    for picture in pictures:
        if isinstance(picture.source, Path):
            shutil.rmtree(picture.source.parent, ignore_errors=True)


def legend(paths: Sequence[Path]) -> str:
    """Return the lines that map `[Image #N]` to its file for the session, or "" without images."""
    lines = [f"[Image #{number}] = {path}" for number, path in enumerate(paths, 1)]
    return "\n".join([LEGEND, *lines]) if lines else ""
