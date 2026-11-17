"""What the loop knows per `app:signature`: `<run root>/app-errors.json` (contract `ledger`).

States: `ticket` (the part is open on the board), `shipped` (its fix is pushed and deployed, the source still
has to be told), `fixed` (the source knows; `fixed_build` and `installed_at` judge later reports).
"""

from __future__ import annotations

import json
import threading
from typing import TYPE_CHECKING, Any

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

FILE = "app-errors.json"
_LOCK = threading.Lock()  # the loop thread and a finishing Ship both write


def load(root: Path) -> dict[str, dict[str, Any]]:
    """Return the ledger; a missing or unreadable file is empty, an entry that is not an object is dropped."""
    try:
        data = json.loads((root / FILE).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


def _save(root: Path, data: dict[str, dict[str, Any]]) -> None:
    atomic.write_text(root / FILE, json.dumps(data, indent=1, sort_keys=True) + "\n")


def put(root: Path, key: str, **fields: object) -> None:
    """Merge `fields` into the entry of `key` (created when missing)."""
    with _LOCK:
        data = load(root)
        data[key] = {**data.get(key, {}), **fields}
        _save(root, data)


def drop(root: Path, key: str) -> None:
    """Forget the entry of `key`; a missing one is fine."""
    with _LOCK:
        data = load(root)
        if data.pop(key, None) is not None:
            _save(root, data)


def mark_shipped(root: Path, keys: Iterable[str], commit: str, now: float) -> None:
    """Move the ticket entries a Ship pushed and deployed in `commit` to `shipped` (resolve is next)."""
    with _LOCK:
        data = load(root)
        for key in keys:
            if data.get(key, {}).get("state") == "ticket":
                data[key] = {**data[key], "state": "shipped", "commit": commit, "shipped_at": now}
        _save(root, data)
