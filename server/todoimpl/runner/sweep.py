"""Free the disk of every run that already rests (T2433): `python -m todoimpl.runner.sweep [--apply]`.

The same cleanup Ship, Close, Cancel and Done manually now do by themselves (`reap.clean`), for the run dirs
those clicks left before it existed; failed runs too (their unpushed branches stay, so Retry still works).
A dry run by default. `--budget` seconds bound one call (the cap is 60 s): exit 3 says "run it again", and a
rerun goes on where this one stopped, since a cleaned run has nothing left to remove.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board import state as store

from . import reap

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

AGAIN = 3


def _args(argv: Sequence[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="python -m todoimpl.runner.sweep", description=__doc__)
    parser.add_argument("--apply", action="store_true", help="remove (default: only list what would go)")
    parser.add_argument("--exclude", action="append", default=[], help="run id to leave alone (repeatable)")
    parser.add_argument("--budget", type=float, default=20.0, help="seconds before it starts no worktree")
    parser.add_argument("--root", type=Path, default=None, help="run root (default $TODOIMPL_HOME)")
    return parser.parse_args(argv)


def _show(rep: reap.Report, *, apply: bool) -> list[str]:
    verb = "removed" if apply else "would remove"
    lines = [f"{verb} {path}" for path in (*rep.removed, *rep.payload)]
    lines += [f"{'deleted' if apply else 'would delete'} branch {b} ({rep.run.name})" for b in rep.branches]
    lines += [f"kept branch {b} ({rep.run.name}): commits no remote has" for b in rep.kept]
    return lines + [f"skipped {why}" for why in rep.skipped]


def main(argv: Sequence[str] | None = None, *, clock: Callable[[], float] = time.monotonic) -> int:
    """Clean (or list) every resting run under the root; print one line per path."""
    args = _args(argv)
    root: Path = args.root or store.run_root()
    runs = sorted(p for p in root.iterdir() if (p / "state.json").is_file() and p.name not in args.exclude)
    start = clock()
    for done, run in enumerate(runs):
        # Asked before each worktree too: one run can hold 14 of them (20 GB), more than one call's 60 s.
        rep = reap.clean(run, apply=args.apply, ok=lambda: clock() - start <= args.budget)
        if rep.refused == reap.TAKEN or clock() - start > args.budget:
            for line in _show(rep, apply=args.apply):
                print(line)
            print(f"budget spent after {done} of {len(runs)} runs: run it again")
            return AGAIN
        if rep.refused and not rep.refused.startswith("stage "):
            print(f"left {run.name}: {rep.refused}")
        for line in _show(rep, apply=args.apply):
            print(line)
    print(f"{len(runs)} runs looked at")
    return 0


if __name__ == "__main__":
    sys.exit(main())
