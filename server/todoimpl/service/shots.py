"""Screenshots of a run: the png bytes under `<run dir>/shots`, never anything that resolves outside it."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def read_shot(directory: Path, name: str) -> bytes | None:
    """Bytes of the png at `name` (a/b.png) under `<directory>/shots`; None when it resolves outside it."""
    shots = (directory / "shots").resolve()
    parts = name.split("/")
    if name.startswith("/") or any(p in ("", ".", "..") for p in parts) or not name.endswith(".png"):
        return None
    path = (shots / name).resolve()
    if not path.is_relative_to(shots) or not path.is_file():
        return None
    try:
        return path.read_bytes()
    except OSError:
        return None
