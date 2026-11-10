"""Durable file writes: a power loss or SIGKILL leaves the old file or the whole new one, never a torn one.

`write_text` writes a unique temp file beside the target, fsyncs it, renames it over the target and fsyncs the
directory so the rename itself survives. `append_line` appends one line and fsyncs (a torn last line is
tolerated by the readers of the jsonl logs). Every state, round, issue and mark file goes through here
(`tests/test_atomic.py` fails when a module writes a temp file and renames it by hand).
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


def write_text(path: Path, text: str) -> None:
    """Replace `path` with `text` atomically and durably; the old file stays whole if anything fails."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp.unlink()
        raise
    _fsync_dir(path.parent)


def append_line(path: Path, line: str) -> None:
    """Append `line` (a newline is added) and fsync it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as out:
        out.write(line.rstrip("\n") + "\n")
        out.flush()
        os.fsync(out.fileno())
