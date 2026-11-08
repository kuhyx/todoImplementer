"""The host of one claude turn: `python -m todoimpl.runner.turnhost <run_dir> <stem>`.

The server never owns claude: it launches this host (a transient systemd unit in production) and tails files.
The host reads `<stem>.invoke.json` (argv, cwd, env; mode 0600, deleted at once: the env holds secrets), runs
claude with stdout going straight into `<stem>.stream.jsonl` (a file, not a pipe: nobody has to be reading),
fills the pids into `turn.pid`, and when claude exits writes `<stem>.exit.json` atomically. A restarted server
therefore finds the turn alive, or finished with its result on disk. SIGTERM (a stop of the unit) is passed to
claude's process group and still ends with an exit record.

Everything is imported up front and no shell script is involved: an edit of the checkout while a turn runs
cannot change what a live host does.
"""

from __future__ import annotations

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

from . import orphans
from .files import EXIT_SUFFIX, STREAM_SUFFIX, sibling, write_json

if TYPE_CHECKING:
    from collections.abc import Sequence
    from types import FrameType

INVOKE_SUFFIX = ".invoke.json"
ERR_SUFFIX = ".stderr.log"
GRACE = 3.0  # seconds between the SIGTERM passed on and the SIGKILL
TICK = 0.2
SUPERSEDED = 125
BAD_INVOCATION = 126
SPAWN_FAILED = 127


class Stop:
    """Signal handler: pass SIGTERM to claude's group, SIGKILL it when it lingers past `GRACE`."""

    def __init__(self) -> None:  # noqa: D107
        self.proc: subprocess.Popen[bytes] | None = None
        self.at: float | None = None

    def __call__(self, signum: int, frame: FrameType | None) -> None:  # noqa: ARG002
        """Forward the first signal; claude's own group is its pid (it runs in a new session)."""
        if self.proc is not None and self.at is None:
            self.at = time.monotonic()
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGTERM)

    def escalate(self) -> None:
        """SIGKILL the group once the grace after a forwarded signal is over."""
        if self.proc is not None and self.at is not None and time.monotonic() - self.at >= GRACE:
            with contextlib.suppress(ProcessLookupError):
                os.killpg(self.proc.pid, signal.SIGKILL)


def _finish(run_dir: Path, stem: str, code: int, pid: int | None, error: str | None = None) -> int:
    """Write the exit record; its appearance is what tells the server the turn is over."""
    record: dict[str, object] = {"code": code, "ended": time.time(), "pid": pid}
    if error is not None:
        record["error"] = error
    write_json(sibling(run_dir, stem, EXIT_SUFFIX), record)
    return 0


def _wait(proc: subprocess.Popen[bytes], stop: Stop) -> int:
    while True:
        try:
            return proc.wait(timeout=TICK)
        except subprocess.TimeoutExpired:
            stop.escalate()


def run(run_dir: Path, stem: str, stop: Stop) -> int:
    """Run the turn to its end and record how it ended; return the host's own exit status (0)."""
    path = sibling(run_dir, stem, INVOKE_SUFFIX)
    try:
        inv = json.loads(path.read_text(encoding="utf-8"))
        path.unlink()
        argv, cwd, env = list(inv["argv"]), inv["cwd"], dict(inv["env"])
    except OSError, ValueError, KeyError, TypeError:
        return _finish(run_dir, stem, BAD_INVOCATION, None, "the invocation file is missing or unreadable")
    rec = orphans.read(run_dir)
    if (
        rec is None or rec.stem != stem
    ):  # declared lost while this host was starting: do not run beside its successor
        return _finish(run_dir, stem, SUPERSEDED, None, "the server no longer waits for this turn")
    try:
        with (
            sibling(run_dir, stem, STREAM_SUFFIX).open("ab") as out,
            sibling(run_dir, stem, ERR_SUFFIX).open("ab") as err,
        ):
            proc = subprocess.Popen(  # noqa: S603 - the argv claude.build made, no shell
                argv,
                cwd=cwd,
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=err,
                start_new_session=True,
            )
    except OSError as exc:
        return _finish(run_dir, stem, SPAWN_FAILED, None, str(exc))
    stop.proc = proc
    me = os.getpid()
    orphans.write(
        run_dir, pid=proc.pid, start=orphans.start_of(proc.pid), host_pid=me, host_start=orphans.start_of(me)
    )
    return _finish(run_dir, stem, _wait(proc, stop), proc.pid)


def main(argv: Sequence[str] | None = None) -> int:
    """Install the stop handlers and run the turn named by `<run_dir> <stem>`."""
    run_dir, stem = (sys.argv[1:3] if argv is None else argv)[:2]
    stop = Stop()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return run(Path(run_dir), stem, stop)


if __name__ == "__main__":
    sys.exit(main())
