"""Repo step: after a green gate, run the repo's `coverage-gaps` and file its uncovered files as tickets.

The command is the repo's own CLAUDE.md bullet (`- coverage-gaps: `coverage-gaps coverage.xml``), run in the
board worktree right after the gate wrote the report, with `--json --max-files 10` so one visit files at
most ten tickets (the worst files first). One ticket per repo and file (`nolimit-coverage-<sha8 of path>`):
the same file seen again counts up, never files twice. Exit 2 (the report is unreadable: the gate wrote
none) is one ticket of its own. A repo with no such bullet is skipped.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from . import steps, tickets

if TYPE_CHECKING:
    from pathlib import Path

    from .repos import Repo

OUT = ".nolimit-gaps.json"
MAX_FILES = 10


def command(repo: Repo) -> str | None:
    """Return the gaps command as JSON into `OUT`, exit 0 for covered and gaps alike; None without one."""
    base = repo.commands.get("coverage-gaps")
    if not base or not base.startswith("coverage-gaps"):
        return None
    return f"{base} --json --max-files {MAX_FILES} > {OUT}; c=$?; [ $c -le 1 ] || exit $c"


def gaps(wt: Path) -> list[dict[str, Any]]:
    """Return the report's files, then remove the report (it must not reach a commit)."""
    out = wt / OUT
    try:
        data = json.loads(out.read_text(encoding="utf-8"))
    except OSError, ValueError:
        data = {}
    out.unlink(missing_ok=True)
    files = data.get("files") if isinstance(data, dict) else None
    return [f for f in files if isinstance(f, dict) and isinstance(f.get("path"), str)] if files else []


def run(repo: Repo, wt: Path, now: float) -> list[str]:
    """Run the step and file its tickets; return the signatures filed (empty when covered or skipped)."""
    cmd = command(repo)
    if cmd is None:
        return []
    done = steps.run("coverage-gaps", cmd, wt)
    if done.slow:
        tickets.slow(repo, done, now)
        return []
    if not done.passed:
        (wt / OUT).unlink(missing_ok=True)
        return tickets.red(repo, done, now)
    return [tickets.gap(repo, f, now) for f in gaps(wt)]
