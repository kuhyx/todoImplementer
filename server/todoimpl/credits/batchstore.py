"""Pending batches (T2532): `<root>/batches.json`, one row per one-shot key, so a restart picks them up again.

A key is `<kind>:<prompt hash>`: the caller asks again with the same prompt (its retry after a failure) and
finds its batch. A row holds the batch id, kind, model, when it went out, when it was last polled and the
estimate the pace counts while it runs. Rows go when their batch ends; a row older than a day (the API's
24 h limit) is dropped as expired.
"""

from __future__ import annotations

import hashlib
import json
import threading
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

FILE = "batches.json"
MAX_AGE_S = 86400.0
LOCK = threading.Lock()


def key(kind: str, prompt: str) -> str:  # noqa: D103
    return f"{kind}:{hashlib.sha256(prompt.encode()).hexdigest()[:16]}"


def _read(root: Path) -> dict[str, dict[str, Any]]:
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _write(root: Path, rows: dict[str, dict[str, Any]]) -> None:
    atomic.write_text(root / FILE, json.dumps(rows, indent=1, sort_keys=True))


def get(root: Path, name: str) -> dict[str, Any] | None:  # noqa: D103
    with LOCK:
        return _read(root).get(name)


def put(root: Path, name: str, row: dict[str, Any]) -> None:  # noqa: D103
    with LOCK:
        rows = _read(root)
        rows[name] = row
        _write(root, rows)


def drop(root: Path, name: str) -> None:  # noqa: D103
    with LOCK:
        rows = _read(root)
        if rows.pop(name, None) is not None:
            _write(root, rows)


def pending(root: Path, now: float | None = None) -> list[dict[str, Any]]:
    """Return the pending rows, oldest first; with `now`, rows past the 24 h limit are left out."""
    rows = sorted(_read(root).values(), key=lambda r: float(r.get("submitted_at", 0)))
    return [r for r in rows if now is None or now - float(r.get("submitted_at", 0)) < MAX_AGE_S]


def view(root: Path, now: float) -> dict[str, Any]:
    """Return the contract's `batches` object: how many are pending, their estimate and the oldest's age."""
    rows = pending(root, now)
    oldest = float(rows[0]["submitted_at"]) if rows else None
    est = sum(float(r.get("est_usd", 0)) for r in rows)
    return {"pending": len(rows), "est_usd": est, "oldest_at": oldest}
