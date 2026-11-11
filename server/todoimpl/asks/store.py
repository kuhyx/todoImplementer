"""Per-card ask state in `<run dir>/asks.json`: first-seen times and one record per ask id."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "asks.json"


def load(directory: Path) -> dict[str, Any]:
    """Return {"seen": {id: ts}, "items": {id: record}, "log": [str]}; a missing or corrupt file is empty."""
    try:
        data = json.loads((directory / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return {
        "seen": dict(data.get("seen") or {}),
        "items": dict(data.get("items") or {}),
        "log": list(data.get("log") or []),
    }


def save(directory: Path, data: dict[str, Any]) -> None:
    """Write the state durably."""
    atomic.write_text(directory / FILE, json.dumps(data, ensure_ascii=False, indent=1))
