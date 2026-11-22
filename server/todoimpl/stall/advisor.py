"""Advisor calls still waiting on their answer, on any thread of a turn's stream (T2448, T2486).

The advisor model answers a `server_tool_use` call in 60-140 s and nothing streams meanwhile. A background
sub-agent's call can sit far back in the stream while the main thread has already ended its turn, so the
newest line alone does not show it (card 3f9de200-0, 2026-11-22): the whole stream is matched by id, each
call (`server_tool_use.id`) against its answer (`tool_use_id`). Only lines naming a `srvtoolu_` id are parsed.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

ADVISOR = 240.0  # s an unanswered advisor call counts as work
CAP = 16 * 1024 * 1024  # bytes read from the end of the stream: a call older than that has long timed out
ID = b"srvtoolu_"


def stamp(row: dict[str, object]) -> float | None:
    """Return the epoch time of a stream line's ISO `timestamp`, None when it has none."""
    try:
        return datetime.fromisoformat(str(row["timestamp"])).timestamp()
    except KeyError, ValueError:
        return None


def _blocks(row: object) -> list[dict[str, object]]:
    """Return the content blocks of a message line (`assistant` or `user`), [] for anything else."""
    if not isinstance(row, dict) or row.get("type") not in {"assistant", "user"}:
        return []
    message = row.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


def pending_until(path: Path) -> float | None:
    """Return until when the stream's unanswered advisor calls count as work: the latest call + `ADVISOR`."""
    try:
        with path.open("rb") as fh:
            fh.seek(0, os.SEEK_END)
            fh.seek(max(0, fh.tell() - CAP))
            data = fh.read()
    except OSError:
        return None
    calls: dict[object, float] = {}
    answered: set[object] = set()
    for line in data.splitlines():
        if ID not in line:
            continue
        try:
            row = json.loads(line)
        except ValueError:  # claude is mid-write, or the cap cut the line
            continue
        at = stamp(row) if isinstance(row, dict) else None
        for block in _blocks(row):
            if block.get("type") == "server_tool_use" and at is not None:
                calls[block.get("id")] = at
            answered.add(block.get("tool_use_id"))
    pending = [at for call, at in calls.items() if call not in answered]
    return max(pending) + ADVISOR if pending else None
