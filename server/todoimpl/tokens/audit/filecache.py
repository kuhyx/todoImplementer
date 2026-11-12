"""Persistent per-transcript cache for the token audit (T1997).

Transcripts are append-only and 7 GB in size, so a rerun that re-reads all of
them cannot finish inside the 60 s action cap. Each derived result (note facts,
a window session, lifetime spend) is stored under the transcript's path and
stamped with its size and ``mtime_ns``; a changed file simply misses and is
parsed again. The cache is best effort: an unreadable, torn or unwritable entry
is a miss, never an error, and a hit returns exactly what a parse would.

Location: ``$TODOIMPL_HOME/cache/audit``, else ``$XDG_CACHE_HOME/todoimpl/audit``,
else ``~/.cache/todoimpl/audit``. Hits touch the entry so only entries unused
for a long time age out in :func:`prune`.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

from todoimpl import atomic

DAY_SECONDS = 86400
# Entries nobody has read for this long are dropped (per-kind overrides below).
MAX_IDLE_DAYS = 90
IDLE_DAYS = {"session": 14}


def cache_dir() -> Path:
    """Directory holding the entries, resolved on each call (tests change HOME)."""
    home = os.environ.get("TODOIMPL_HOME")
    if home:
        return Path(home) / "cache" / "audit"
    xdg = os.environ.get("XDG_CACHE_HOME")
    base = Path(xdg) if xdg else Path.home() / ".cache"
    return base / "todoimpl" / "audit"


def _entry(kind: str, path: Path) -> Path:
    digest = hashlib.sha1(str(path).encode(), usedforsecurity=False).hexdigest()
    return cache_dir() / kind / f"{digest}.json"


def _signature(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_size, stat.st_mtime_ns]


def load(kind: str, path: Path, extra: str = "") -> Any | None:  # noqa: ANN401
    """Return the stored payload for an unchanged file, else ``None``."""
    entry = _entry(kind, path)
    try:
        stored = json.loads(entry.read_text(encoding="utf-8"))
        fresh = stored["path"] == str(path) and stored["sig"] == _signature(path) and stored["extra"] == extra
        payload = stored["data"] if fresh else None
        if fresh:
            os.utime(entry)
    except OSError, ValueError, KeyError, TypeError:
        return None
    return payload


def store(kind: str, path: Path, payload: Any, extra: str = "") -> None:  # noqa: ANN401
    """Save ``payload`` for the file's current signature; failures are ignored."""
    try:
        body = {"path": str(path), "sig": _signature(path), "extra": extra, "data": payload}
        atomic.write_text(_entry(kind, path), json.dumps(body, separators=(",", ":")), durable=False)
    except OSError:
        return


def prune(now: float | None = None) -> int:
    """Delete entries idle past their kind's limit; return how many went."""
    stamp = time.time() if now is None else now
    gone = 0
    for entry in cache_dir().glob("*/*.json"):
        limit = IDLE_DAYS.get(entry.parent.name, MAX_IDLE_DAYS) * DAY_SECONDS
        try:
            if stamp - entry.stat().st_mtime > limit:
                entry.unlink()
                gone += 1
        except OSError:
            continue
    return gone
