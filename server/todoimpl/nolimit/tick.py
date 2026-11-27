"""One no-limit tick, the server's loop around it, and the CLI.

`tick()`: while the trigger holds, visit the next repo of the cycle (one repo per tick). The server runs it
on its own thread every `INTERVAL` seconds (`Loop`, started by `service.build_backend`).

CLI: `python -m todoimpl.nolimit.tick --repo <name> --once [--no-push]`. `--repo` visits that checkout now,
whatever the trigger says (a manual run); without it the tick asks the trigger like the server does.
Without `--once` the CLI loops like the server.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.board.clone import src_root
from todoimpl.board.state import run_root
from todoimpl.runner import freeok

from . import chores, repos, run, status, trigger
from .worktree import home

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

log = logging.getLogger("todoimpl.nolimit")
INTERVAL = 300.0


def tick(
    root: Path, clock: Callable[[], float] = time.time, gateway_up: Callable[[], bool] = freeok.gateway_up,
    *, push: bool = True,
) -> str | None:  # fmt: skip
    """Visit the next repo, then run the next board chore, while the trigger holds.

    Return the visit's result, None when the runner rests (or no repo is left to visit).
    """
    active = trigger.holds(root, clock(), gateway_up)
    status.set_active(root, active=active)
    if not active:
        return None

    def still() -> bool:
        return trigger.holds(root, clock(), gateway_up)

    repo = status.pick(root, repos.discover(src_root()))
    result = None if repo is None else visit(root, repo, clock, still, push=push)
    if still():
        name, report = chores.tick(root, still, clock=clock)
        log.info("no-limit chore %s: %s", name, json.dumps(report)[:300])
    return result


def visit(
    root: Path, repo: repos.Repo, clock: Callable[[], float], still: Callable[[], bool], *, push: bool
) -> str:
    """Visit `repo` and record its result."""
    now = clock()
    result = run.visit(repo, now, still, push=push)
    status.finish(root, repo.name, result, clock())
    log.info("no-limit %s: %s", repo.name, result)
    return result


class Loop:
    """The server's thread: `tick()` every `interval` seconds until `stop()`."""

    def __init__(
        self, root: Path, *, interval: float = INTERVAL, step: Callable[[Path], object] = tick
    ) -> None:
        """Nothing runs until `start()`."""
        self.root, self.interval, self._step = root, interval, step
        self._stop = threading.Event()

    def start(self) -> Loop:
        """Start the thread; return the loop."""
        threading.Thread(target=self.run_forever, name="nolimit", daemon=True).start()
        return self

    def stop(self) -> None:
        """Stop after the current tick."""
        self._stop.set()

    def run_forever(self) -> None:
        """Tick until `stop()`; a failed tick is logged and the next one runs on time."""
        while not self._stop.is_set():
            try:
                self._step(self.root)
            except Exception:
                log.exception("no-limit tick failed")
            self._stop.wait(self.interval)


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI; print the tick's result as JSON. Exit 1 when the named repo is no checkout of kuhy's."""
    parser = argparse.ArgumentParser(prog="python -m todoimpl.nolimit.tick")
    parser.add_argument("--repo", help="visit this ~/src checkout now, whatever the trigger says")
    parser.add_argument("--once", action="store_true", help="one tick, then exit")
    parser.add_argument("--no-push", action="store_true", help="commit on the branch, never push or deploy")
    parser.add_argument(
        "--chore", choices=chores.NAMES, help="run this board chore now, whatever the trigger"
    )
    args = parser.parse_args(argv)
    root, push = run_root(), not args.no_push
    if args.chore is not None:
        name, report = chores.tick(root, lambda: True, args.chore)
        print(json.dumps({"chore": name, "report": report}))
        return 0
    if args.repo is None and not args.once:
        Loop(root, step=lambda r: tick(r, push=push)).run_forever()
        return 0
    if args.repo is None:
        print(json.dumps({"result": tick(root, push=push)}))
        return 0
    repo = repos.load(src_root() / args.repo)
    if repo is None:
        print(json.dumps({"error": f"{args.repo}: no checkout with a kuhyx origin under {src_root()}"}))
        return 1
    result = visit(root, repo, time.time, lambda: True, push=push)
    print(json.dumps({"repo": repo.name, "result": result, "branch_dir": str(home() / repo.name)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
