"""The prompt line that points a turn at the context the no-limit runner precomputed (`nolimit.context`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.nolimit.context import path

if TYPE_CHECKING:
    from pathlib import Path


def pointer(run_dir: Path) -> list[str]:
    """Return the line naming `<run>/nolimit-context.md`, none when the runner wrote no file for this card."""
    found = path(run_dir)
    if not found.is_file():
        return []
    return [f"Precomputed while Claude was out (commits, diff, changed-file tests): read {found} first."]
