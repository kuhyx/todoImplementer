"""A repo's `make test` check runs a sharded suite as its steps, each on its own build ticket (T2487).

`make test` of todoImplementer ran as one pytest run, so the board's check held one build slot for the whole
suite (58-79 s). A Makefile that has `test-shard`, `test-cov` and `SHARDS ?= <n>` gets its `make test` run as
`make test-shard SHARD=k` for k in 1..n into one coverage dir, then `make test-cov`; each step queues for the
lock on its own, so no slot is held for the whole suite. Any other check runs as it is.
"""

from __future__ import annotations

import re
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .lanes import Timing

COMMAND = "make test"
TARGETS = (re.compile(r"^test-shard\s*:", re.MULTILINE), re.compile(r"^test-cov\s*:", re.MULTILINE))
SHARDS = re.compile(r"^SHARDS\s*\??=\s*(\d+)\s*$", re.MULTILINE)


def steps(command: str, cwd: Path, cov_dir: Path) -> list[str]:
    """Return the commands that run `command`: the shard steps of a sharded `make test`, else itself."""
    try:
        text = (cwd / "Makefile").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [command]
    count = SHARDS.search(text)
    if command != COMMAND or count is None or not all(t.search(text) for t in TARGETS):
        return [command]
    where = shlex.quote(str(cov_dir))
    shards = [f"make test-shard SHARD={k} COV_DIR={where}" for k in range(1, int(count.group(1)) + 1)]
    return [*shards, f"make test-cov COV_DIR={where}"]


def add(total: Timing, step: Timing) -> tuple[str, float, float, str]:
    """Add a step's queue and run seconds to the check's; return the step's lane, seconds and holder."""
    total.lane, total.queue_s, total.run_s = step.lane, total.queue_s + step.queue_s, total.run_s + step.run_s
    total.holder = total.holder or step.holder
    return step.lane, step.queue_s, step.run_s, step.holder
