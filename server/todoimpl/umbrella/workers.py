"""The worker attempt log: one JSON line per `claude-free` run, in `<umbrella run dir>/free-workers.jsonl`.

Written by `runner/freeworker.py` (start, end, exit code, whether a signal killed it, the worker log path);
read by the tracking view (what ran, for how long, where its log is) and by the free-token view (the time
windows in which our workers called the gateway).
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "free-workers.jsonl"


def record(run_dir: Path, row: dict[str, Any]) -> None:
    """Append one attempt: child, attempt, start, end, exit, killed, log."""
    atomic.append_line(run_dir / FILE, json.dumps(row))


def read(run_dir: Path) -> list[dict[str, Any]]:
    """Return the attempts in file order; a torn or hand-written bad line is skipped."""
    try:
        text = (run_dir / FILE).read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        try:
            found = json.loads(line)
        except ValueError:
            continue
        if isinstance(found, dict):
            rows.append(found)
    return rows
