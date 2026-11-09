"""Two small files under the run root: "credits exhausted until the limit lifts" and the overage alert."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

EXHAUSTED_FILE = "credits-exhausted"
ALERT_FILE = "overage-alert.json"


def _write(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    tmp.write_text(json.dumps(data) + "\n", encoding="utf-8")
    tmp.replace(path)


def _read(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def mark_exhausted(root: Path, until: float, detail: str) -> None:
    """Record that the free credits ran out; it holds until `until` (the plan limit's end)."""
    _write(root / EXHAUSTED_FILE, {"until": until, "detail": detail[:300]})


def exhausted(root: Path, now: float) -> bool:
    """Return True while a recorded exhaustion has not yet reached its `until`."""
    until = _read(root / EXHAUSTED_FILE).get("until")
    return isinstance(until, int | float) and until > now


def clear_exhausted(root: Path) -> None:  # noqa: D103
    (root / EXHAUSTED_FILE).unlink(missing_ok=True)


def raise_alert(root: Path, text: str, until: float) -> None:
    """Record the overage alert; the board shows it until `until`."""
    _write(root / ALERT_FILE, {"kind": "overage", "text": text, "until": until})


def active_alert(root: Path, now: float) -> dict[str, Any] | None:
    """Return the board's `alert` object while its `until` lies ahead, else None."""
    found = _read(root / ALERT_FILE)
    until, text = found.get("until"), found.get("text")
    if isinstance(until, int | float) and until > now and isinstance(text, str) and text:
        return {"kind": "overage", "text": text, "until": float(until)}
    return None
