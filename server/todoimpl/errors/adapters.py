"""Source adapters: turn what an app's error pipeline wrote into contract records.

`kartka` maps kartka's own `state.json` (`DOCS-error-reports.md` in that repo); `contract` reads a file that
is already in the contract's shape (`~/.local/state/app-errors/<app>.json`): a new app writes one.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from .record import AppError, parse

if TYPE_CHECKING:
    from pathlib import Path

MESSAGE_MAX = 300
BUILD_FIELDS = ("build", "versionCode")


class SourceError(Exception):
    """A source file that cannot be read or is not in the shape its adapter expects."""


def _load(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        msg = f"{path}: {exc}"
        raise SourceError(msg) from exc


def _dict(value: object) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _build(*places: object) -> int:
    """Return the first build number any of the dicts names (kartka's state carries none today), else 0."""
    for place in places:
        for name in BUILD_FIELDS:
            value = place.get(name) if isinstance(place, dict) else None
            if isinstance(value, int) and not isinstance(value, bool) and value > 0:
                return value
    return 0


def _detail(entry: dict[str, Any]) -> str | None:
    """One line of what kartka knows around the error: routes, sources, how many devices."""
    parts = []
    for label, name in (("routes", "routes"), ("sources", "sources")):
        found = [str(v) for v in entry.get(name) or [] if v]
        if found:
            parts.append(f"{label} {', '.join(found)}")
    if devices := entry.get("devices"):
        parts.append(f"devices {len(devices)}")
    return "; ".join(parts) or None


def _kartka_record(sig: str, entry: dict[str, Any], app: str, repo: str) -> AppError | None:
    sample: dict[str, Any] = _dict(entry.get("sample"))
    kinds = entry.get("kinds") if isinstance(entry.get("kinds"), list) else []
    message = str(sample.get("error") or entry.get("type") or "")[:MESSAGE_MAX]
    where = entry.get("where")
    return parse(
        {
            "app": app,
            "repo": repo,
            "signature": str(entry.get("id") or sig),
            "kind": str(kinds[0] if kinds else sample.get("kind") or "error"),
            "message": message,
            "top_frame": where if isinstance(where, str) else None,
            "count": max(1, entry["count"]) if isinstance(entry.get("count"), int) else 1,
            "first_seen": entry.get("first"),
            "last_seen": entry.get("last"),
            "build": _build(entry, sample),
            "version_name": sample.get("versionName") if isinstance(sample.get("versionName"), str) else None,
            "detail": _detail(entry),
            "open": entry.get("resolved") is None,
        }
    )


def kartka(path: Path, app: str, repo: str) -> list[AppError]:
    """Return one record per signature of kartka's state.json; resolved ones come back with `open` false."""
    data = _load(path)
    found = data.get("signatures") if isinstance(data, dict) else None
    if not isinstance(found, dict):
        msg = f"{path}: no `signatures` object"
        raise SourceError(msg)
    records = (
        _kartka_record(str(sig), entry, app, repo) for sig, entry in found.items() if isinstance(entry, dict)
    )
    return [record for record in records if record is not None]


def contract(path: Path) -> list[AppError]:
    """Return the valid records of a file in the contract's `report` shape; bad records are dropped."""
    data = _load(path)
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("errors"), list):
        msg = f"{path}: not a version 1 error report"
        raise SourceError(msg)
    return [record for raw in data["errors"] if (record := parse(raw)) is not None]
