"""A sub-agent's request to the model, from its transcript: still out, or answered with N tokens (T2563).

claude writes an `api-request` line to a sub-agent's transcript when it sends the request and the answer's
message lines when each block is done, each with its `usage.output_tokens`. Nothing in between: no partial
line of a sub-agent reaches any file, so a sub-agent thinking for two minutes looks exactly like one whose
request hangs. Only the answer tells them apart.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .advisor import stamp
from .output import OUTPUT, UNDECIDED, rows, walk

if TYPE_CHECKING:
    from pathlib import Path

REQUEST = "api-request"


def _asked(lines: list[bytes], _mtime: float) -> object:
    for _back, row in rows(lines):
        if not isinstance(row, dict) or (at := stamp(row)) is None:
            continue
        if row.get("type") == REQUEST:
            return at
        if row.get("type") in OUTPUT:
            return None  # the newest line is a message: no request is out
    return UNDECIDED


def asked(path: Path) -> float | None:
    """Return when the transcript's request still waiting on its answer was sent, None when none waits."""
    found = walk(path, _asked, default=None)
    return found if isinstance(found, float) else None


def _tokens(row: dict[str, object]) -> int:
    message = row.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    count = usage.get("output_tokens") if isinstance(usage, dict) else None
    return count if isinstance(count, int) else 0


def answer(path: Path, sent: float) -> tuple[float, int] | None:
    """Return when the request sent at `sent` got its first answer line and its output tokens, None before."""

    def _decide(lines: list[bytes], _mtime: float) -> object:
        first: tuple[float, int] | None = None
        for _back, row in rows(lines):
            if not isinstance(row, dict) or (at := stamp(row)) is None:
                continue
            if row.get("type") == "assistant":
                first = (at, _tokens(row))  # walking back: the last one met is the first after the request
            elif row.get("type") == REQUEST and at == sent:
                return first
            elif row.get("type") in {REQUEST, "user"}:
                first = None  # a later exchange: its answer is not this request's
        return UNDECIDED

    found = walk(path, _decide, default=None)
    return found if isinstance(found, tuple) else None
