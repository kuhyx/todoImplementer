"""The host of one pre-push gate: `python -m todoimpl.runner.gatehost <run_dir> <worktree>` (see gate.py).

Runs `scripts/check_gate_stamp.sh step <id>` per manual-stage hook, one capped command each, stopping at the
first red one, and writes `<run_dir>/gate/exit.json` (`tree`, `ok`, one row per step) when it is over: the
server only waits for that file. Whatever goes wrong, the record is written.
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .checks import CheckResult, clean_env, run_check
from .files import write_json

if TYPE_CHECKING:
    from collections.abc import Sequence

STAMP_TOOL = "scripts/check_gate_stamp.sh"
LIST_TIMEOUT = 50.0
STEP_TIMEOUT = 1800.0
STEP_ENV = {"CAP_MEM": "4G", "CAP_CPU_PCT": "25"}  # a gate step may need more than capped.sh's 2 GiB default
TAIL = 600


def _row(r: CheckResult) -> dict[str, Any]:
    return {"name": r.name, "command": r.command, "exit": r.exit_code, "tail": r.tail, "log": r.log}


def _ids(wt: Path) -> list[str]:
    """Return the manual-stage hook ids; a failing listing raises CalledProcessError with its output."""
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["bash", STAMP_TOOL, "full", "--list"],  # noqa: S607
        cwd=wt, env=clean_env(), capture_output=True, text=True, timeout=LIST_TIMEOUT, check=False,
    )  # fmt: skip
    if done.returncode:
        raise subprocess.CalledProcessError(done.returncode, "full --list", done.stdout, done.stderr)
    return done.stdout.split()


def run(run_dir: Path, wt: Path) -> dict[str, Any]:
    """Run every step and return the record; `[]` hooks means the stamp is written directly."""
    tree = subprocess.run(
        ["git", "rev-parse", "HEAD^{tree}"],  # noqa: S607
        cwd=wt, capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    rows: list[dict[str, Any]] = []
    try:
        ids = _ids(wt)
    except subprocess.CalledProcessError as exc:
        rows.append(
            _row(CheckResult("gate-list", exc.cmd, exc.returncode, (exc.stderr or exc.stdout)[-TAIL:], ""))
        )
    except (OSError, subprocess.SubprocessError) as exc:
        rows.append(_row(CheckResult("gate-list", "full --list", None, str(exc)[-TAIL:], "")))
    else:
        for step in ids or [""]:
            name, command = (f"gate-{step}", f"step {step}") if step else ("gate-write", "write")
            result = run_check(name, f"{STAMP_TOOL} {command}", wt, run_dir, STEP_TIMEOUT, STEP_ENV)
            rows.append(_row(result))
            if not result.passed:
                break
    return {"tree": tree, "ok": all(row["exit"] == 0 for row in rows), "steps": rows, "ended": time.time()}


def main(argv: Sequence[str] | None = None) -> int:
    """Run the gate named by `<run_dir> <worktree>` and write its record."""
    run_dir, wt = (sys.argv[1:3] if argv is None else argv)[:2]
    write_json(Path(run_dir) / "gate" / "exit.json", run(Path(run_dir), Path(wt)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
