"""A turn stream's newest output, read from the end, further back when one line outgrows the tail (T2560).

The board reads only the last `BOARD_TAIL` bytes of a stream, but claude writes single lines bigger than
that (card bcf6a474-0, 2026-11-27: a 73,501-byte `system commands_changed` skill list right after a tool
result), so the tail held one cut line and no message. A read that decides nothing reads 4x as far back,
up to `CAP`.
"""

from __future__ import annotations

import json
import os
from typing import TYPE_CHECKING

from .advisor import ADVISOR
from .advisor import CAP as _ADVISOR_CAP
from .advisor import stamp as _stamp

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

BOARD_TAIL = 64 * 1024  # the board polls every running card, so the first read is short
CAP = _ADVISOR_CAP  # bytes: the farthest back a reader looks
GROW = 4
PARTIAL = "stream_event"  # a chunk of the message the model writes now (`--include-partial-messages`)
THINKING = "thinking_tokens"  # claude's estimate of the thinking so far, written while the model thinks
OUTPUT = frozenset({"assistant", "user"})  # stream lines that are real work: a message, or a tool's result
UNDECIDED = object()  # a walk that met nothing deciding: read further back


def _tails(path: Path) -> Iterator[tuple[list[bytes], float]]:
    """Yield the file's whole last lines and its mtime, from further back each time, to the start or `CAP`."""
    size = BOARD_TAIL
    while True:
        with path.open("rb") as fh:
            end = fh.seek(0, os.SEEK_END)
            start = max(0, end - size)
            fh.seek(max(0, start - 1))
            data = fh.read()
            mtime = os.fstat(fh.fileno()).st_mtime
        if start:  # drop the cut first line; a byte before it tells whether the tail starts on a line
            data = data[1:] if data[:1] == b"\n" else data.partition(b"\n")[2]
        yield data.splitlines(), mtime
        if not start or size >= CAP:
            return
        size *= GROW


def _rows(lines: list[bytes]) -> Iterator[tuple[int, object]]:
    """Yield each parsed line from the newest back, with how many lines are newer; a torn line is skipped."""
    for back, line in enumerate(reversed(lines)):
        try:
            yield back, json.loads(line)
        except ValueError:  # claude is mid-write
            continue


def _walk(path: Path, decide: Callable[[list[bytes], float], object], *, default: object) -> object:
    try:
        for lines, mtime in _tails(path):
            if (found := decide(lines, mtime)) is not UNDECIDED:
                return found
    except OSError:
        pass
    return default


def _pending_advisor(row: dict[str, object]) -> bool:
    """Tell whether a message line ends on a server tool call (the advisor) whose answer has not come."""
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    last = content[-1] if isinstance(content, list) and content else None
    return isinstance(last, dict) and last.get("type") == "server_tool_use"


def _writing(row: object) -> bool:
    """Tell whether a stream line is one claude writes only while the model streams (T2452, T2469).

    While the model thinks, claude interleaves `system thinking_tokens` lines with the `thinking_delta`
    events, so the last line is often such a system line.
    """
    if not isinstance(row, dict):
        return False
    return row.get("type") == PARTIAL or (row.get("type") == "system" and row.get("subtype") == THINKING)


def _newest(lines: list[bytes], mtime: float) -> object:
    for back, row in _rows(lines):
        if not isinstance(row, dict) or row.get("type") not in OUTPUT:
            if back == 0 and _writing(row):
                return mtime  # the model is writing its answer or thinking right now (T2452, T2469)
            continue
        at = _stamp(row)
        if at is None:
            return mtime if back == 0 else None
        return at + ADVISOR if _pending_advisor(row) else at
    return UNDECIDED


def newest(path: Path) -> float | None:
    """Return when the stream's newest message or tool result line was written; see `scan.last_output`."""
    found = _walk(path, _newest, default=None)
    return found if isinstance(found, float) else None


def _ended(lines: list[bytes], _mtime: float) -> object:
    for _back, row in _rows(lines):
        kind = row.get("type") if isinstance(row, dict) else None
        if kind == "result":
            return True
        if kind in OUTPUT:
            return False
    return UNDECIDED


def ended(path: Path) -> bool:
    """Return True when a `result` line comes after the stream's last message line (T2505)."""
    return _walk(path, _ended, default=False) is True
