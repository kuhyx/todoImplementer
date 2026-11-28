"""The `sym` tool of board sessions: its dir on a turn's PATH, and the index built with a worktree."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

log = logging.getLogger(__name__)

BIN = Path(__file__).resolve().parents[3] / "scripts" / "bin"  # holds `sym` (scripts/bin/sym)


def start(wt: Path) -> None:
    """Build `wt`'s ctags index in a detached process; the turn never waits and a failure never stops it.

    `sym --index` writes `<git dir>/tags` atomically; `sym <name>` builds it itself if this is not done.
    """
    try:
        subprocess.Popen(  # noqa: S603 - argv list, no shell
            [str(BIN / "sym"), "--index"],
            cwd=wt,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except OSError:
        log.warning("sym index for %s did not start", wt, exc_info=True)
