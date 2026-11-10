"""Wait for free workers in code: `freeworker wait <log>... [--timeout S]` replaces the manager's polling.

A worker records itself beside its log: `<log>.pid` while it runs, `<log>.exit` (its exit code) when over.
`wait` blocks until every given log has an exit record, or the time is up, and prints one line per worker. The
manager's model is then called once per wait instead of once per poll, and only to diagnose and coach.
A worker whose process is gone without an exit record (killed) is `lost`: reported, never waited for.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl import atomic

if TYPE_CHECKING:
    from collections.abc import Sequence

DEFAULT_TIMEOUT = 540.0  # under the Bash tool's 600 s ceiling
POLL = 1.0
START_GRACE = 30.0  # a worker with no pid file after this long never started
STILL_RUNNING = 6  # exit code of `wait` when the time ran out with workers still running
EXIT, PID = ".exit", ".pid"
SUMMARY_CHARS = 160


def _beside(log: Path, suffix: str) -> Path:
    return log.with_name(log.name + suffix)


def mark_started(log: Path) -> None:
    """Record this process as the running worker of `log`."""
    log.parent.mkdir(parents=True, exist_ok=True)
    _beside(log, EXIT).unlink(missing_ok=True)  # a rerun on the same log is not finished yet
    atomic.write_text(_beside(log, PID), str(os.getpid()))


def mark_exit(log: Path, code: int) -> None:
    """Record the worker's exit code (atomically) and drop its pid file."""
    atomic.write_text(_beside(log, EXIT), str(code))
    _beside(log, PID).unlink(missing_ok=True)


def exit_of(log: Path) -> int | None:
    """Return the recorded exit code of the worker of `log`, None while there is none."""
    try:
        return int(_beside(log, EXIT).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return None


def _alive(log: Path, *, grace_over: bool) -> bool:
    """Say whether the worker of `log` can still write an exit record (its pid file names a live process).

    No pid file yet counts as alive for `START_GRACE`: the worker may still be starting.
    """
    try:
        pid = int(_beside(log, PID).read_text(encoding="utf-8"))
    except OSError, ValueError:
        return not grace_over
    return Path(f"/proc/{pid}").exists()


def wait(logs: Sequence[Path], timeout: float, poll: float = POLL) -> dict[Path, str]:
    """Block until every worker has an exit record or is lost; return the logs still running at `timeout`."""
    begun = time.monotonic()
    deadline = begun + timeout
    while True:
        grace_over = time.monotonic() - begun >= START_GRACE
        running = {
            log: "running" for log in logs if exit_of(log) is None and _alive(log, grace_over=grace_over)
        }
        if not running or time.monotonic() >= deadline:
            return running
        time.sleep(poll)


def _tail(log: Path) -> str:
    """Return the worker's last words: the last line of its log that is not a startup warning."""
    from .freeworker import answer  # noqa: PLC0415 - freeworker imports this module

    try:
        text = log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    lines = answer(text).splitlines()
    return lines[-1][:SUMMARY_CHARS] if lines else ""


def summary(logs: Sequence[Path], running: dict[Path, str]) -> list[str]:
    """Return one line per worker: `<log>: exit=<code> <last words>`, `running` or `lost`."""
    out = []
    for log in logs:
        code = exit_of(log)
        if log in running:
            out.append(f"{log.name}: running")
        elif code is None and not _beside(log, PID).exists():
            out.append(f"{log.name}: not started (no pid file after {START_GRACE:g} s)")
        elif code is None:
            out.append(f"{log.name}: lost (the worker died without an exit record) {_tail(log)}".rstrip())
        else:
            out.append(f"{log.name}: exit={code} {_tail(log)}".rstrip())
    return out


def main(argv: Sequence[str]) -> int:
    """Run `wait <log>... [--timeout S]`: print the summary; exit 0 when all finished, 6 when some run."""
    import argparse  # noqa: PLC0415 - only the wait command parses arguments here

    parser = argparse.ArgumentParser(prog="freeworker wait")
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    args = parser.parse_args(argv)
    running = wait(args.logs, args.timeout)
    for line in summary(args.logs, running):
        print(line, flush=True)
    if running:
        print(f"{len(running)} of {len(args.logs)} still running: call wait again", flush=True)
        return STILL_RUNNING
    print(f"all {len(args.logs)} workers finished", flush=True)
    return 0
