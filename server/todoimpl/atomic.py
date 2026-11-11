"""Durable file writes: a power loss or SIGKILL leaves the old file or the whole new one, never a torn one.

`write_text` (`write_bytes` for binary) writes a unique temp file beside the target, fsyncs it, renames it
over the target and fsyncs the directory so the rename itself survives. `append_line` appends one line and
fsyncs (a torn last line is tolerated by the readers of the jsonl logs). Every state, round, issue and mark
file goes through here (`tests/test_atomic.py` fails when a module writes a temp file and renames it by hand).
"""

from __future__ import annotations

import contextlib
import os
import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def _fsync_dir(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write_text(path: Path, text: str, *, durable: bool = True, mode: int | None = None) -> None:
    """Replace `path` with `text` atomically and, unless `durable` is off, durably.

    The old file stays whole if anything fails. `durable=False` skips the two fsyncs for a file that is
    rewritten many times a second and can be rebuilt (the live-feed offset): a rename is still atomic.
    `mode` is set on the temp file, so an executable never shows up without its x bit.
    """
    write_bytes(path, text.encode("utf-8"), durable=durable, mode=mode)


def write_bytes(path: Path, data: bytes, *, durable: bool = True, mode: int | None = None) -> None:
    """Replace `path` with `data` the way `write_text` does (images, any binary file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp.open("wb") as handle:
            handle.write(data)
            handle.flush()
            if durable:
                os.fsync(handle.fileno())
        if mode is not None:
            tmp.chmod(mode)
        tmp.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    if durable:
        _fsync_dir(path.parent)


def append_line(path: Path, line: str) -> None:
    """Append `line` (a newline is added) and fsync it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(line.rstrip("\n") + "\n")
        out.flush()
        os.fsync(out.fileno())
