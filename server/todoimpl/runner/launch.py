"""Start a turn host detached from the server, and stop one by its record.

Production: `systemd-run --user` makes the host a transient unit of its own (control-group kill mode), so the
turn survives any restart, deploy or crash of the server. A transient unit does not inherit the server's
environment (probed 2026-11-08: none of the server's CLAUDE_* variables arrive), so argv, cwd and env travel
in a mode-0600 JSON file the host deletes. `TODOIMPL_TURN_LAUNCH=direct` (tests) starts the same host as a
plain detached child instead: tests never call systemd-run.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from . import buildlock, cardslice, orphans
from .files import ROUTE_SUFFIX, STREAM_SUFFIX, NeedsYouError, sibling
from .turnhost import INVOKE_SUFFIX

if TYPE_CHECKING:
    from .claude import Invocation

LAUNCH_VAR = "TODOIMPL_TURN_LAUNCH"
SERVER_DIR = Path(__file__).resolve().parents[2]  # what the host needs on PYTHONPATH: `todoimpl` lives here
TIMEOUT_VAR = "TODOIMPL_TURN_TIMEOUT"  # seconds a turn may run before its host kills it
DEFAULT_TIMEOUT = 4 * 3600.0  # above a manager round: a 1 h worker plus coaching reruns
UNIT_STOP_SEC = 10
# deploy/todoimpl.slice: every board unit (turn, gate, deploy) shares one memory/swap/CPU cap (T1982); each
# runs one level down in its own capped slice (cardslice.py, T2405). OOMPolicy=continue: a build below claude
# killed for memory fails its command, the turn goes on.
SLICE = cardslice.PARENT
START_WAIT = 2.0  # how long stop() waits for a just-launched host to record claude's pid
POLL = 0.05
_run = subprocess.run  # the one place systemd-run and systemctl are called: tests swap it


def direct() -> bool:
    """Say whether `$TODOIMPL_TURN_LAUNCH` asks for a plain detached child instead of a systemd unit."""
    return os.environ.get(LAUNCH_VAR, "systemd") == "direct"


def unit_name(card: str, stem: str) -> str:
    """`todoimpl-turn-<card>-<stem>` with only the characters a unit name allows."""
    return "todoimpl-turn-" + re.sub(r"[^A-Za-z0-9_.-]", "_", f"{card}-{stem}")


def host_argv(run_dir: Path, stem: str) -> list[str]:
    """Return the host's command line (no shell script: a live host never reads a file that may be edited)."""
    return [sys.executable, "-m", "todoimpl.runner.turnhost", str(run_dir), stem]


def systemd_argv(unit: str, run_dir: Path, stem: str) -> list[str]:
    """`systemd-run` argv for the host; the env is deliberately not here, only the host's PYTHONPATH."""
    return [
        "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
        f"--slice={cardslice.card_slice(run_dir.name)}", "-p", "KillMode=control-group",
        "-p", f"TimeoutStopSec={UNIT_STOP_SEC}", "-p", "OOMPolicy=continue",
        "-E", f"PYTHONPATH={SERVER_DIR}",
        "--", *host_argv(run_dir, stem),
    ]  # fmt: skip


@dataclass(frozen=True)
class Handle:
    """A turn in flight, adopted or fresh: `stop()` ends it; `detach` makes its follower let go of it."""

    run_dir: Path
    stem: str
    unit: str | None
    detach: threading.Event = field(default_factory=threading.Event, compare=False)

    def stop(self, grace: float = 3.0) -> None:
        """End the turn: stop its unit, else (direct launch or a failed stop) signal claude's group."""
        if (
            self.unit is not None
            and _run(["systemctl", "--user", "stop", self.unit], capture_output=True).returncode == 0
        ):
            return  # a failed stop (no bus, unit unknown) falls through to the recorded process group
        deadline = time.monotonic() + START_WAIT
        rec = orphans.read(self.run_dir)
        while rec is not None and rec.pid is None and time.monotonic() < deadline:
            time.sleep(POLL)
            rec = orphans.read(self.run_dir)
        if rec is not None:
            orphans.terminate(rec.pid, rec.start, grace)


def handle_for(run_dir: Path, rec: orphans.Record) -> Handle:
    """Return the handle of a recorded turn (it needs a stem; legacy records have none)."""
    return Handle(run_dir, str(rec.stem), rec.unit)


def turn_timeout() -> float:
    """Return the wall-clock limit of one turn: `$TODOIMPL_TURN_TIMEOUT` seconds, default 4 h."""
    try:
        seconds = float(os.environ.get(TIMEOUT_VAR, ""))
    except ValueError:
        return DEFAULT_TIMEOUT
    return seconds if seconds > 0 else DEFAULT_TIMEOUT


def _invocation(inv: Invocation) -> str:
    """Return the host's instructions; the limit travels in the file, so it holds across a server restart.

    `lock` names the build lock: the host does not count the time the turn only waits on it (T2270).
    """
    body = {
        "argv": list(inv.argv), "cwd": str(inv.cwd), "env": inv.env, "timeout": turn_timeout(),
        "lock": str(buildlock.root() / buildlock.LOCK), "peer": inv.peer,
    }  # fmt: skip
    return json.dumps(body)


def _write_private(path: Path, text: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as out:
        out.write(text)


def start(run_dir: Path, stem: str, role: str, inv: Invocation) -> orphans.Record:
    """Record the turn, write its invocation file and launch the host; NeedsYouError if that fails."""
    unit = None if direct() else unit_name(run_dir.name, stem)
    rec = orphans.begin(run_dir, stem, role, unit)
    invoke = sibling(run_dir, stem, INVOKE_SUFFIX)
    _write_private(invoke, _invocation(inv))
    sibling(run_dir, stem, STREAM_SUFFIX).touch()
    sibling(run_dir, stem, ROUTE_SUFFIX).write_text(inv.route + "\n", encoding="utf-8")
    if unit is None:
        host = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            host_argv(run_dir, stem), env={"PYTHONPATH": str(SERVER_DIR)}, start_new_session=True,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )  # fmt: skip
        threading.Thread(
            target=host.wait, daemon=True
        ).start()  # reap the host so it never lingers as a zombie
    else:
        done = _run(systemd_argv(unit, run_dir, stem), capture_output=True, text=True, check=False)
        if done.returncode != 0:
            invoke.unlink(missing_ok=True)
            orphans.clear(run_dir)
            msg = f"could not start the turn unit {unit}: {done.stderr.strip()[:300]}"
            raise NeedsYouError(msg)
    return rec
