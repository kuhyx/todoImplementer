"""Go and Done-rerun on a permission block: run kuhy's one-liner (or trust he did) and rerun the stage."""

from __future__ import annotations

import contextlib
import os
import signal
import subprocess
from typing import TYPE_CHECKING

from todoimpl.board.state import load, run_dir, save
from todoimpl.http.backend import BackendError

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .scheduling import SchedulerLike

TIMEOUT = 55.0
TAIL = 1500
NOTE = (
    "(runner) {who} `{command}`{result}. That unblocks the step you were stopped on: "
    "carry on from there (do not repeat the command if it already ran)."
)


def run_command(command: str, timeout: float = TIMEOUT) -> tuple[int, str]:
    """Run the one-liner as this user (never with a terminal); return (exit code, output tail)."""
    proc = subprocess.Popen(  # noqa: S603 - the command is the one shown on the card, run by kuhy's click
        ["bash", "-c", command],  # noqa: S607
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
        start_new_session=True,
    )
    try:
        out, _ = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.communicate()
        return 124, f"timed out after {timeout:.0f} s"
    return proc.returncode, out.strip()[-TAIL:]


def _command(root: Path, id8: str) -> tuple[str, RunState]:
    run = load(run_dir(root, id8))
    perm = run.extra.get("permission") if run is not None else None
    command = perm.get("command") if isinstance(perm, dict) else None
    if run is None or not command:
        msg = "this card has no command to run"
        raise BackendError("disabled", msg)  # noqa: EM101
    return str(command), run


def _log(scheduler: SchedulerLike, id8: str, now: float, text: str) -> None:
    bus = getattr(scheduler, "bus", None)
    if bus is not None:
        bus.publish(id8, {"type": "activity", "at": now, "kind": "system", "text": text, "tool": None})


def _rerun(root: Path, scheduler: SchedulerLike, run: RunState, note: str) -> None:
    for key in ("permission", "perm_reruns"):
        run.extra.pop(key, None)
    save(run_dir(root, run.task_id), run)
    scheduler.send(run.task_id, note)


def go(
    root: Path,
    scheduler: SchedulerLike,
    id8: str,
    runner: Callable[[str], tuple[int, str]],
    now: float,
) -> None:
    """Run the card's command; exit 0 reruns the blocked stage, anything else is reported."""
    command, run = _command(root, id8)
    code, tail = runner(command)
    shown = f"Go: `{command}` exited {code}" + (f": {tail}" if tail else "")
    _log(scheduler, id8, now, shown)
    if code != 0:
        raise BackendError("conflict", shown)  # noqa: EM101
    result = f" (exit 0{': ' + tail if tail else ''})"
    _rerun(root, scheduler, run, NOTE.format(who="kuhy clicked Go: ran", command=command, result=result))


def rerun(root: Path, scheduler: SchedulerLike, id8: str) -> None:
    """Done, rerun: kuhy ran the command himself in a terminal."""
    command, run = _command(root, id8)
    _rerun(root, scheduler, run, NOTE.format(who="kuhy ran", command=command, result=" himself"))
