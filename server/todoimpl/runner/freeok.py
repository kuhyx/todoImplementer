"""May a card go on the free models now? Never blocks: the engine's queue and the board ask it (T2531).

Repo visibility comes from the cache `free-llm-check-dir` keeps (`~/.cache/omniroute_offload`), the gateway
answer from a probe at most a minute old, run off the caller. Stdlib only, so the board may import it.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path

from . import freegate

VISIBILITY = Path(".cache") / "omniroute_offload" / "visibility.json"
GATEWAY_TTL = 60.0
ERROR_LINE = "Error-Signature:"  # an app-error fix never goes to the free models (T2445)
_gate: dict[str, float | bool] = {"at": float("-inf"), "up": False}
_lock = threading.Lock()


def public(repo: str | None) -> bool:
    """Say whether `repo` (`owner/name`) is cached as PUBLIC; unknown counts as private."""
    if not repo:
        return False
    try:
        cache = json.loads((Path.home() / VISIBILITY).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return False
    entry = cache.get(repo) if isinstance(cache, dict) else None
    return isinstance(entry, dict) and entry.get("visibility") == "PUBLIC"


def _probe() -> None:
    up = freegate.check_gateway()
    with _lock:
        _gate.update(at=time.monotonic(), up=up)


def gateway_up() -> bool:
    """Return the last gateway answer; a stale one starts a new probe in the background."""
    with _lock:
        stale = time.monotonic() - float(_gate["at"]) > GATEWAY_TTL
        if stale:
            _gate["at"] = time.monotonic()  # claim the probe: a burst of calls starts one
        up = bool(_gate["up"])
    if stale:
        threading.Thread(target=_probe, name="free-gateway-probe", daemon=True).start()
    return up


def may_go_free(repo: str | None, body: str | None) -> bool:
    """Say whether a card of `repo` with this note body may run on the free models now."""
    return public(repo) and ERROR_LINE not in (body or "") and gateway_up()
