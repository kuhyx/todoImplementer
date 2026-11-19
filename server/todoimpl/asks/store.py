"""Per-card ask state in `<run dir>/asks.json`: first-seen times and one record per ask id."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

    from .parse import Ask

FILE = "asks.json"


def load(directory: Path, asks: Iterable[Ask] = ()) -> dict[str, Any]:
    """Return {"seen", "items", "rounds", "log"}; a missing or corrupt file is empty.

    `rounds` maps an id to the reply that asked it. An id in `asks` whose reply differs from the saved one
    is a new ask that reuses the id (T2277): its old record and first-seen time are dropped, so it is open.
    A record with no saved round (written before rounds) is adopted into the current one and kept.
    """
    try:
        data = json.loads((directory / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    out: dict[str, Any] = {
        "seen": dict(data.get("seen") or {}),
        "items": dict(data.get("items") or {}),
        "rounds": dict(data.get("rounds") or {}),
        "log": list(data.get("log") or []),
    }
    for ask in asks:
        if out["rounds"].setdefault(ask.id, ask.round) != ask.round:
            out["seen"].pop(ask.id, None)
            out["items"].pop(ask.id, None)
            out["rounds"][ask.id] = ask.round
    return out


def save(directory: Path, data: dict[str, Any]) -> None:
    """Write the state durably."""
    atomic.write_text(directory / FILE, json.dumps(data, ensure_ascii=False, indent=1))
