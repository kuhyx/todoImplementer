"""The server's side of peer delivery: write a line into a live turn's FIFO, then find its replay echo.

The turn host (`runner/peerpipe.py`) owns `<run>/peer.fifo`. A write opens it non-blocking first, so a
FIFO with no reader (or none at all) means no session to deliver to; the line itself then goes in blocking
(claude drains its stdin while it works). The mark is the newest stream file and its size before the write:
the echo with the message's uuid lands after it.
"""

from __future__ import annotations

import contextlib
import json
import os
import stat
from typing import TYPE_CHECKING, Any

from todoimpl.runner.files import STREAM_SUFFIX

if TYPE_CHECKING:
    from pathlib import Path

FIFO = "peer.fifo"
READ_CAP = 16 * 1024 * 1024  # bytes of stream read per echo check


class RunPipe:
    """Peer delivery into the run dirs under one root."""

    def __init__(self, root: Path) -> None:  # noqa: D107
        self._root = root

    def _mark(self, card: str) -> tuple[str, int]:
        streams = sorted((self._root / card).glob(f"*{STREAM_SUFFIX}"), key=lambda p: p.stat().st_mtime)
        return (str(streams[-1]), streams[-1].stat().st_size) if streams else ("", 0)

    def write(self, card: str, line: dict[str, Any]) -> tuple[str, int] | None:
        """Write one stream-json line into the card's live turn; None when no turn reads one."""
        try:
            fd = os.open(self._root / card / FIFO, os.O_WRONLY | os.O_NONBLOCK)
        except OSError:
            return None
        try:
            if not stat.S_ISFIFO(os.fstat(fd).st_mode):
                return None
            os.set_blocking(fd, True)
            mark = self._mark(card)
            data = memoryview((json.dumps(line, ensure_ascii=False) + "\n").encode())
            while data:
                data = data[os.write(fd, data) :]
            return mark
        finally:
            with contextlib.suppress(OSError):
                os.close(fd)

    @staticmethod
    def echoed(card: str, mark: tuple[str, int], uuid: str) -> bool:  # noqa: ARG004 - the hub's Pipe shape
        """Whether the stream replayed the line with this uuid after the mark."""
        path, offset = mark
        try:
            with open(path, "rb") as handle:  # noqa: PTH123 - a str path from the mark
                handle.seek(offset)
                return uuid.encode() in handle.read(READ_CAP)
        except OSError:
            return False

    def is_open(self, card: str) -> bool:
        """Whether the card has a turn that takes peer lines now."""
        return (self._root / card / FIFO).exists()
