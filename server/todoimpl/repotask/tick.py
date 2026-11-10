"""Claude's hand on the parts: `python -m todoimpl.repotask.tick <run dir> done|split|step <part key> ...`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import files


def command(run_dir: Path) -> str:
    """Return the shell prefix a prompt hands to the session (this package on the path, the run dir given)."""
    root = Path(__file__).resolve().parents[2]
    return f"PYTHONPATH={root} {sys.executable} -m todoimpl.repotask.tick {run_dir}"


def main(argv: list[str] | None = None) -> int:
    """Record one tick; print what was recorded or why not (exit 1)."""
    cli = argparse.ArgumentParser(prog="tick", description="Tick a part of the repo task.")
    cli.add_argument("run_dir", type=Path)
    sub = cli.add_subparsers(dest="action", required=True)
    sub.add_parser("done").add_argument("key")
    split = sub.add_parser("split")
    split.add_argument("key")
    split.add_argument("titles", nargs="+")
    step = sub.add_parser("step")
    step.add_argument("key")
    step.add_argument("number", type=int)
    args = cli.parse_args(argv)
    try:
        if args.action == "done":
            files.mark_done(args.run_dir, args.key)
        elif args.action == "split":
            files.split(args.run_dir, args.key, args.titles)
        else:
            files.step_done(args.run_dir, args.key, args.number)
    except files.PartError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"ok: {args.action} {args.key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
