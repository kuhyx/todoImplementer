"""Staged attachments: POST /api/upload streams one file here, the new-task POST claims them by id.

Layout: `<root>/<id>/data` (the bytes) and `<root>/<id>/name` (the name kuhy's file had), root
`$TODOIMPL_UPLOADS_ROOT` or `$TODOIMPL_HOME/uploads`. A file is only here between the two POSTs: the new task
moves it into the dufs folder (`images.attach`), and each upload sweeps what a closed dialog left behind.
"""

from __future__ import annotations

import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import unquote

from todoimpl.board.state import run_root

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

MB = 1024 * 1024
MAX_FILE = 100 * MB
MAX_TASK = 500 * MB
MAX_AGE = 24 * 3600  # a dialog left open longer than this uploads again
MAX_NAME = 200
CHUNK = 64 * 1024
ID = re.compile(r"[0-9a-f]{32}")
CONTROL = re.compile(r"[\x00-\x1f\x7f]")


class ShortBodyError(Exception):
    """The client stopped sending before Content-Length bytes arrived."""


@dataclass(frozen=True)
class Staged:
    """One staged file: its id, original name, size in bytes and where its bytes are."""

    id: str
    name: str
    size: int
    path: Path


def root() -> Path:
    """Return the staging dir."""
    found = os.environ.get("TODOIMPL_UPLOADS_ROOT")
    return Path(found) if found else run_root() / "uploads"


def clean_name(raw: str | None) -> str:
    """Return the file name from the percent-encoded header: no folders, no control characters, capped."""
    name = CONTROL.sub("", unquote(raw or "")).replace("\\", "/").rsplit("/", 1)[-1].strip()
    return name[:MAX_NAME] or "file"


def sweep(base: Path, now: float) -> None:
    """Drop staged files older than MAX_AGE (a dialog closed without Create)."""
    for entry in base.iterdir() if base.is_dir() else ():
        if entry.is_dir() and ID.fullmatch(entry.name) and entry.stat().st_mtime < now - MAX_AGE:
            shutil.rmtree(entry, ignore_errors=True)


def _copy(read: Callable[[int], bytes], size: int, target: Path) -> None:
    with target.open("wb") as out:
        left = size
        while left > 0:
            chunk = read(min(CHUNK, left))
            if not chunk:
                raise ShortBodyError(target)
            out.write(chunk)
            left -= len(chunk)


def stage(read: Callable[[int], bytes], size: int, name: str, base: Path) -> Staged:
    """Stream `size` bytes from `read` into a fresh staging dir; raise ShortBodyError when they stop early."""
    sweep(base, time.time())
    file_id = uuid.uuid4().hex
    folder = base / file_id
    folder.mkdir(parents=True)
    try:
        _copy(read, size, folder / "data")
        (folder / "name").write_text(name, encoding="utf-8")
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise
    return Staged(file_id, name, size, folder / "data")


def claim(ids: Sequence[str], base: Path) -> tuple[Staged, ...] | str:
    """Return the staged files for `ids` in order, or why they cannot make one task."""
    found: list[Staged] = []
    for file_id in ids:
        folder = base / file_id
        if not ID.fullmatch(file_id) or not (folder / "name").is_file():
            return f"attachment {file_id} is gone: attach it again"
        data = folder / "data"
        found.append(
            Staged(file_id, (folder / "name").read_text(encoding="utf-8"), data.stat().st_size, data)
        )
    if sum(s.size for s in found) > MAX_TASK:
        return f"attachments total over {MAX_TASK // MB} MB"
    return tuple(found)
