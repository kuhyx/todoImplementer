"""Tolerant readers for a run's `*.stream.jsonl` files (claude -p --output-format stream-json)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


def stream_files(run_dir: Path) -> list[Path]:
    """Stream files of one run, name-sorted (plan before implement is not implied)."""
    return sorted(run_dir.glob("*.stream.jsonl"))


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield every JSON-object line; blank, torn or non-object lines are skipped.

    A live session appends to the file, so the last line may be half-written.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj
