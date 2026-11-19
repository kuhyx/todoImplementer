"""The todo app's images on kuhy's dufs: where they live here, how notes link them, how a session reads them.

A note links an image as `![](https://kuhy-cloud.duckdns.org/todo-images/<folder>/<file>.<ext>)`; the same
file is `<root>/<folder>/<file>.<ext>` on this PC (root: `$TODOIMPL_IMAGES_ROOT`, default
`~/data/cloud/todo-images`). A headless session cannot log in to dufs, so its prompt carries the local path.
"""

from __future__ import annotations

import os
import re
import shutil
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from .uploads import Staged

URL = "https://kuhy-cloud.duckdns.org/todo-images"
LINK = re.compile(re.escape(URL) + r"/([A-Za-z0-9_-]+)/([A-Za-z0-9_-]+\.[a-z0-9]{1,10})(?![A-Za-z0-9])")
EXTENSION = re.compile(r"[a-z0-9]{1,10}")  # the todo app's own rule (attachment_ref.dart), so it renders them
UNKNOWN = "bin"
INLINE = frozenset({"jpg", "jpeg", "png", "gif", "webp", "bmp", "avif", "heic", "heif", "svg"})


def root(env: Mapping[str, str] | None = None) -> Path:
    """Return the local folder behind the dufs `todo-images` URL."""
    env = os.environ if env is None else env
    if found := env.get("TODOIMPL_IMAGES_ROOT"):
        return Path(found)
    return Path(env.get("HOME") or Path.home()) / "data" / "cloud" / "todo-images"


def extension_of(name: str) -> str:
    """Return the lower-cased extension when it is 1-10 letters or digits, else UNKNOWN."""
    stem, dot, ext = name.rpartition(".")
    return ext.lower() if dot and stem and EXTENSION.fullmatch(ext.lower()) else UNKNOWN


def label(name: str) -> str:
    """Return `name` safe as a markdown link label (brackets and line breaks would end the link)."""
    text = re.sub(r"[\r\n]+", " ", name.replace("[", "(").replace("]", ")")).strip()
    return text or "file"


def attach(files: Sequence[Staged], base: Path, folder: str) -> tuple[str, ...]:
    """Move staged files to `<base>/<folder>/<uuid>.<ext>`; answer `![](url)` or `[name](url)` for each."""
    lines = []
    for staged in files:
        ext = extension_of(staged.name)
        file = f"{uuid.uuid4()}.{ext}"
        (base / folder).mkdir(parents=True, exist_ok=True)
        shutil.move(staged.path, base / folder / file)
        shutil.rmtree(staged.path.parent, ignore_errors=True)
        url = f"{URL}/{folder}/{file}"
        lines.append(f"![]({url})" if ext in INLINE else f"[{label(staged.name)}]({url})")
    return tuple(lines)


def copy_into(paths: Sequence[Path], run_dir: Path) -> tuple[Path, ...]:
    """Copy each file to `<run_dir>/attachments/<folder>/<file>`; answer the copy, else the source."""
    out = []
    for path in paths:
        copy = run_dir / "attachments" / path.parent.name / path.name
        try:
            if path.is_file() and not copy.is_file():
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, copy)
        except OSError:
            pass  # the session still reads the source under the images root
        out.append(copy if copy.is_file() else path)
    return tuple(out)


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
