"""Run one repo command as a no-limit step: capped.sh, a hard 60 s cut, the output's tail kept.

The command runs as `timeout -k 5 60 bash -c <command>` inside `checks.run_capped` (capped.sh, its own process
group, the build lock or light slot first): `timeout` cuts it at 60 s even if the server dies meanwhile, and
`run_capped`'s own wait (10 s later) kills the tree as a backstop. A cut step is `slow`, never red.
"""

from __future__ import annotations

import shlex
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.runner.checks import run_capped

if TYPE_CHECKING:
    from collections.abc import Mapping

LIMIT = 60.0
KILL_AFTER = 5
BACKSTOP = 10.0
TIMEOUT_EXITS = (124, 137)  # `timeout`'s own exit when it cut the command (TERM, then KILL)
TAIL_LINES = 40


@dataclass(frozen=True)
class Step:
    """One step's outcome; `exit_code` None means it was cut at the limit."""

    name: str
    command: str
    exit_code: int | None
    tail: str
    seconds: float

    @property
    def passed(self) -> bool:
        """Say whether the step exited 0."""
        return self.exit_code == 0

    @property
    def slow(self) -> bool:
        """Say whether the step was cut at the limit."""
        return self.exit_code is None


def wrapped(command: str, limit: float) -> str:
    """Return the command under `timeout`, so the cut holds without the server."""
    return f"timeout -k {KILL_AFTER} {limit:g} bash -c {shlex.quote(command)}"


def run(
    name: str, command: str, cwd: Path, env: Mapping[str, str] | None = None, limit: float = LIMIT
) -> Step:
    """Run `command` in `cwd` and return its step; a run that `timeout` cut or that outlived it is slow."""
    with tempfile.TemporaryFile("w+", encoding="utf-8", errors="replace") as out:
        began = time.monotonic()
        code = run_capped(wrapped(command, limit), cwd, limit + BACKSTOP, out, env)
        seconds = time.monotonic() - began
        out.seek(0)
        lines = out.read().splitlines()
    if code in TIMEOUT_EXITS and seconds >= limit - 1:
        code = None
    return Step(name, command, code, "\n".join(lines[-TAIL_LINES:]).strip(), round(seconds, 1))


def failed(name: str, command: str, why: str) -> Step:
    """Return a red step for a git plumbing failure (fetch, worktree add): it ran outside capped.sh."""
    return Step(name, command, 1, why, 0.0)
