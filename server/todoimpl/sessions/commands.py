"""Command seam: every subprocess the session mutations spawn goes through here.

Tests inject a fake runner, so no test opens a terminal.

Every call is ``shell=False`` with an explicit timeout and ``check=False``: a
request that hangs because one CLI wedged is worse than one that reports it.
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from typing import Protocol

DEFAULT_TIMEOUT = 10.0


@dataclass(frozen=True, slots=True)
class CommandResult:
    """The outcome of one command, including the failures.

    ``returncode`` is ``None`` when the command never ran to completion --
    timed out, or the binary was missing. Callers distinguish "ran and said no"
    from "could not be asked" on that field.
    """

    argv: tuple[str, ...]
    returncode: int | None
    stdout: str
    stderr: str
    timed_out: bool = False
    error: str | None = None

    @property
    def ok(self) -> bool:
        """True when the command ran and exited zero."""
        return self.returncode == 0


class CommandRunner(Protocol):
    """The seam every collector depends on instead of ``subprocess``."""

    def run(self, argv: tuple[str, ...], timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
        """Execute ``argv`` and return its outcome, never raising."""


class SubprocessRunner:
    """The production :class:`CommandRunner`, backed by ``subprocess.run``."""

    def run(self, argv: tuple[str, ...], timeout: float = DEFAULT_TIMEOUT) -> CommandResult:
        """Execute ``argv``, converting every failure mode into a result."""
        try:
            completed = subprocess.run(  # noqa: S603 - argv tuple built by resume.build_argv, shell=False
                list(argv),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                argv=argv,
                returncode=None,
                stdout="",
                stderr="",
                timed_out=True,
                error=f"timed out after {timeout}s",
            )
        except (OSError, subprocess.SubprocessError) as exc:
            return CommandResult(argv=argv, returncode=None, stdout="", stderr="", error=str(exc))
        return CommandResult(
            argv=argv,
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )
