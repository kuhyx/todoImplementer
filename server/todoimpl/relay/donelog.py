"""The done-log of guard 5 (DOCS-native-app-relay.md): rid -> the result it was answered with.

A replayed rid gets its recorded result and never runs again. Write-kind results also go to a JSON-lines
file (appended and fsynced before the result PUT), so a worker that restarts after a refused result PUT
answers the rid from the file instead of running the click a second time (T2611). Read-kind results stay in
memory only: they change nothing, and a shot can be megabytes. Rows older than KEEP_MS are dropped on load:
a request that old is refused as `expired` anyway, so it cannot run again either.
"""

from __future__ import annotations

import json
import logging
import time
from collections import OrderedDict
from typing import TYPE_CHECKING, Any, Final

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

log = logging.getLogger("todoimpl.relay")
KEPT: Final = 1024  # rids remembered in memory
KEEP_MS: Final = 48 * 3600 * 1000  # twice the 24 h request expiry


class DoneLog:
    """Results by rid: the last KEPT in memory, write kinds also on disk at `path` (None: memory only)."""

    def __init__(self, path: Path | None, now_ms: int | None = None) -> None:
        """Load the rows of `path` younger than KEEP_MS and rewrite the file without the rest."""
        self.path = path
        self._rows: OrderedDict[str, dict[str, Any]] = OrderedDict()
        if path is None or not path.is_file():
            return
        cutoff = (int(time.time() * 1000) if now_ms is None else now_ms) - KEEP_MS
        kept = []
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
                rid, at, result = str(row["rid"]), int(row["at"]), dict(row["result"])
            except (ValueError, KeyError, TypeError) as exc:
                log.warning("relay: done-log line skipped: %s", exc)
                continue
            if at >= cutoff:
                self._keep(rid, result)
                kept.append(line)
        atomic.write_text(path, "".join(f"{line}\n" for line in kept))

    def get(self, rid: str) -> dict[str, Any] | None:
        """Return the recorded result of `rid`, or None."""
        return self._rows.get(rid)

    def add(self, rid: str, result: dict[str, Any], *, durable: bool) -> dict[str, Any]:
        """Record `rid` (on disk too when `durable` and a path is set); return `result`."""
        if durable and self.path is not None:
            row = {"rid": rid, "at": int(time.time() * 1000), "result": result}
            atomic.append_line(self.path, json.dumps(row, separators=(",", ":")))
        self._keep(rid, result)
        return result

    def _keep(self, rid: str, result: dict[str, Any]) -> None:
        self._rows[rid] = result
        self._rows.move_to_end(rid)
        while len(self._rows) > KEPT:
            self._rows.popitem(last=False)
