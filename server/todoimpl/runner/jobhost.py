"""The host of one `run_job` command: `python -m todoimpl.runner.jobhost <run_dir> <id>` (runner/jobs.py).

Reads `<run>/jobs/<id>.invoke.json` (cwd, env, command; deleted at once: the env may hold secrets), runs
`bash -lc <command>` with stdout and stderr together in `<id>.out`, and writes `<id>.exit.json` atomically
when it ends. A SIGTERM (a stop of the unit, Cancel) goes to the command's process group and still ends
with a record.
"""

from __future__ import annotations

import json
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

from .files import write_json
from .turnhost import BAD_INVOCATION, SPAWN_FAILED, Stop

TICK = 0.2
BASH = shutil.which("bash") or "/bin/bash"
DIR = "jobs"  # <run>/jobs/<id>.invoke.json, <id>.out, <id>.exit.json


def path(run: Path, jid: str, suffix: str) -> Path:
    """Return a job's file: `<run>/jobs/<id><suffix>`."""
    return run / DIR / f"{jid}{suffix}"


def _finish(run: Path, jid: str, code: int, error: str | None = None) -> int:
    record: dict[str, object] = {"code": code, "ended": time.time()}
    if error is not None:
        record["error"] = error
    write_json(path(run, jid, ".exit.json"), record)
    return 0


def run(run_dir: Path, jid: str, stop: Stop) -> int:
    """Run the command to its end and record its exit code (128 + N when a signal N ended it)."""
    invoke = path(run_dir, jid, ".invoke.json")
    try:
        inv = json.loads(invoke.read_text(encoding="utf-8"))
        invoke.unlink()
        command, cwd, env = str(inv["command"]), str(inv["cwd"]), dict(inv["env"])
    except OSError, ValueError, KeyError, TypeError:
        return _finish(run_dir, jid, BAD_INVOCATION, "the invocation file is missing or unreadable")
    try:
        with path(run_dir, jid, ".out").open("ab") as out:
            proc = subprocess.Popen(  # noqa: S603 - the command is the session's own, run as it would be
                [BASH, "-lc", command], cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                stderr=subprocess.STDOUT, start_new_session=True,
            )  # fmt: skip
    except OSError as exc:
        return _finish(run_dir, jid, SPAWN_FAILED, str(exc))
    stop.proc = proc
    while True:
        try:
            code = proc.wait(timeout=TICK)
            break
        except subprocess.TimeoutExpired:
            stop.escalate()
    return _finish(run_dir, jid, 128 - code if code < 0 else code)


def main() -> int:
    """Install the stop handlers and run the job named by `<run_dir> <id>`."""
    stop = Stop()
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    return run(Path(sys.argv[1]), sys.argv[2], stop)


if __name__ == "__main__":
    sys.exit(main())
