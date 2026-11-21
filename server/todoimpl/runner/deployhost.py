"""The host of one deploy: `python -m todoimpl.runner.deployhost <run_dir> <worktree> <command>`.

Runs the repo's declared deploy command in the worktree (one capped command, after any gate or deploy already
running) and writes `<run_dir>/deploy/exit.json` (`commit`, `ok`, `exit`, `command`, `tail`, `log`) when it is
over: the server only waits for that file. A command that outlives `TIMEOUT` is killed and recorded as no exit
code. Whatever goes wrong, the record is written, so the server never waits for a unit that has died silently.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from . import checks, stepwatch
from .checks import run_check, timing_row
from .files import root_of, write_json
from .gatehost import LOCK_NAME, exclusive

if TYPE_CHECKING:
    from collections.abc import Sequence

DEPLOY_DIR = checks.DEPLOY_DIR
EXIT_FILE = "exit.json"
TIMEOUT = 1800.0  # an APK build and install; the unit's RuntimeMaxSec (deploy.UNIT_MAX) must stay above it
ENV = {"CAP_MEM": "4G", "CAP_CPU_PCT": "20"}  # a build may need more than capped.sh's 2 GiB default
TAIL = 600
NOT_RUN = 127  # the shell's "command not found": the command could not even start


def run(run_dir: Path, wt: Path, command: str) -> dict[str, Any]:
    """Run `command` and return the record."""
    commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],  # noqa: S607
        cwd=wt, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    row: dict[str, Any] = {"commit": commit, "command": command, "log": ""}
    try:
        result = run_check("deploy", command, wt, run_dir / DEPLOY_DIR, TIMEOUT, ENV)
    except (OSError, subprocess.SubprocessError) as exc:  # e.g. capped.sh is gone
        row.update(exit=NOT_RUN, tail=str(exc)[-TAIL:])
    else:
        row.update(
            exit=result.exit_code, tail=result.tail, log=f"{DEPLOY_DIR}/{result.log}", **timing_row(result)
        )
    return {**row, "ok": row["exit"] == 0, "ended": time.time()}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the deploy named by `<run_dir> <worktree> <command>` and write its record."""
    args = list(sys.argv[1:] if argv is None else argv)
    run_dir, wt, command = Path(args[0]), Path(args[1]), args[2]
    with (
        exclusive(root_of(run_dir) / LOCK_NAME),
        stepwatch.watching(stepwatch.host_watch(run_dir / DEPLOY_DIR / stepwatch.WAIT_FILE)),
    ):
        record = run(run_dir, wt, command)
    write_json(run_dir / DEPLOY_DIR / EXIT_FILE, record)
    return 0


if __name__ == "__main__":
    sys.exit(main())
