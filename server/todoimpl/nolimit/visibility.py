"""Chore: refresh the repo visibility cache, so the free route knows which cards are public.

`free-llm-check-dir <repo>` keeps `~/.cache/omniroute_offload/visibility.json` (one `gh repo view` per repo,
cached a day); `runner.freeok.public` reads it and counts a missing entry as private. The chore runs the
tool, as a capped step under 60 s, for every `~/src` repo whose entry is missing or has lapsed (`STALE`, the
tool's own TTL), oldest first. The tool answers an entry under a day old from its cache without
rewriting it, so running it earlier refreshes nothing (T2616); the free route reads an entry of any age.
Exit 2 is the tool's "private": a refresh too.
The tool missing is an error the report names, never a silent pass.
"""

from __future__ import annotations

import json
import shlex
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.clone import src_root
from todoimpl.runner import freeok

from . import repos, steps

if TYPE_CHECKING:
    from collections.abc import Callable

TOOL = "free-llm-check-dir"
STALE = 86400.0  # the tool's own TTL (`_privacy.CACHE_TTL_S`): younger entries it will not refetch
BUDGET = 45.0
REFUSED = 2  # the tool's exit for a repo that may not go to free models (private): still refreshed


def cache() -> dict[str, dict[str, object]]:
    """Return the visibility cache; an unreadable one is empty."""
    try:
        data = json.loads((Path.home() / freeok.VISIBILITY).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def _age(entry: object, now: float) -> float:
    at = entry.get("at") if isinstance(entry, dict) else None
    return now - at if isinstance(at, int | float) else float("inf")


def run(
    still: Callable[[], bool], now: float, clock: Callable[[], float] = time.monotonic
) -> dict[str, object]:
    """Refresh stale entries until the budget is spent; return the report."""
    tool = shutil.which(TOOL)
    if tool is None:
        return {"error": f"{TOOL} is not on PATH", "refreshed": []}
    known = cache()
    stale = [r for r in repos.discover(src_root()) if _age(known.get(r.slug), now) >= STALE]
    stale.sort(key=lambda r: -_age(known.get(r.slug), now))
    began = clock()
    refreshed: list[str] = []
    failed: list[str] = []
    for repo in stale:
        if not still() or clock() - began > BUDGET:
            break
        done = steps.run("visibility", f"{shlex.quote(tool)} {shlex.quote(str(repo.path))}", repo.path)
        ok = done.exit_code in {0, REFUSED} and _age(cache().get(repo.slug), time.time()) < STALE
        (refreshed if ok else failed).append(repo.slug)
    return {"refreshed": refreshed, "failed": failed, "stale_left": len(stale) - len(refreshed) - len(failed)}
