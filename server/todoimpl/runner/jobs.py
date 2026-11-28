"""`run_job`: a long command runs as its own unit while the session's turn ends (DOCS-peer.md, "Jobs").

A session that waits on a build burns tokens on every poll. The `run_job` tool of the `peer` MCP server
asks the board (`POST /api/peer/job`) to run `bash -lc <command>` in the card's worktree, as a transient
unit in the card's slice with the turn's own env (`claude.turn_env`). The board writes `<run>/job.json`,
ends the turn at its next boundary (`arm`), waits for the unit (`jobwait.hold`), then resumes the same
session with `job <id> (<command>) exited <code>` and the last 40 lines of the output. Everything is on
disk (`<run>/job.json`, `<run>/jobs/<id>.{out,exit.json}`), so a server restart finds the job and goes on.
"""

from __future__ import annotations

import json
import re
import secrets
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl import atomic
from todoimpl.board.parse import StateError
from todoimpl.board.state import load, run_dir
from todoimpl.peer.limits import Refusal

from . import buildlock, claude, launch, orphans, worktree
from .files import read_json, write_json
from .jobhost import DIR, path

if TYPE_CHECKING:
    from collections.abc import Callable

    from .session import Situation
    from .stream import StreamParser

JOB = "job.json"  # the card's one job: id, name, command, unit, host pid, started
HOST = "todoimpl.runner.jobhost"
TAIL = 40  # output lines the resume prompt carries
LINE_CAP = 400  # characters of one output line (a progress bar must not fill the prompt)
MAX_COMMAND = 8000
LOST = 255  # the exit code reported for a job whose unit vanished (reboot, kill) with no exit record
STARTED = "job {id} started; the turn ends now, you will be resumed with the result"
_NAME = re.compile(r"[^A-Za-z0-9_.-]+")


def unit_name(card: str, jid: str) -> str:
    """`todoimpl-job-<card>-<id>`: only characters a unit name allows."""
    return "todoimpl-job-" + re.sub(r"[^A-Za-z0-9_.-]", "_", f"{card}-{jid}")


def active(run: Path) -> dict[str, Any] | None:
    """Return the card's job record, None without one."""
    found = read_json(run / JOB)
    return found if isinstance(found, dict) and found.get("id") else None


def start(root: Path, card: str, command: str, name: str = "") -> dict[str, Any]:
    """Start `command` as the card's job; return `{id, name, message}`. Refusal says why it may not."""
    run = run_dir(root, card)
    try:
        state = load(run)
    except StateError:
        state = None
    if state is None or (not state.worktree and not state.closing):
        msg = f"task {card} has no worktree to run a job in"
        raise Refusal(msg, code="not_found")
    if not command.strip() or len(command.encode()) > MAX_COMMAND:
        msg = f"the command is empty or over {MAX_COMMAND // 1000} KB"
        raise Refusal(msg)
    if (old := active(run)) is not None:
        msg = f"job {old['id']} ({old['command'][:60]}) is still running: end your turn, you will be resumed"
        raise Refusal(msg, code="disabled")
    cwd = worktree.turn_dir(state, state.repo)
    jid = secrets.token_hex(3)
    unit = None if launch.direct() else unit_name(card, jid)
    env = claude.turn_env(cwd)
    env["PATH"] = f"{buildlock.ensure(buildlock.root())}:{env.get('PATH', '')}"  # build shims
    (run / DIR).mkdir(exist_ok=True)
    invoke = path(run, jid, ".invoke.json")
    atomic.write_text(invoke, json.dumps({"cwd": str(cwd), "env": env, "command": command}), mode=0o600)
    clean = _NAME.sub("-", name).strip("-")[:40]
    record = {"id": jid, "name": clean, "command": command, "unit": unit, "started": time.time()}
    write_json(run / JOB, record)  # before the host runs: a restart in between still finds the job
    pid, err = launch.start_unit(unit or f"direct-{jid}", run, HOST, jid)
    if err:
        invoke.unlink(missing_ok=True)
        (run / JOB).unlink(missing_ok=True)
        msg = f"could not start the job unit: {err}"
        raise Refusal(msg, code="disabled")
    if pid is not None:
        write_json(run / JOB, record | {"host_pid": pid, "host_start": orphans.start_of(pid)})
    return {"id": jid, "name": clean, "message": STARTED.format(id=jid)}


def exit_code(run: Path, job: dict[str, Any]) -> int | None:
    """Return the job's exit code; None while it runs; LOST when its unit is gone without an exit record."""
    found = read_json(path(run, job["id"], ".exit.json"))
    if isinstance(found, dict) and isinstance(found.get("code"), int):
        return int(found["code"])
    if job.get("unit"):
        gone = not launch.unit_active(job["unit"])
    else:
        gone = not orphans.alive(job.get("host_pid"), job.get("host_start"))
    if gone and read_json(path(run, job["id"], ".exit.json")) is None:  # it may have just written it
        return LOST
    return None


def tail(run: Path, jid: str) -> str:
    """Return the last `TAIL` lines of the job's combined output, long lines clipped."""
    try:
        lines = path(run, jid, ".out").read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    return "\n".join(line[:LINE_CAP] for line in lines[-TAIL:])


def take(run: Path) -> str:
    """Return the resume text of the finished job and drop its record; empty without a job."""
    job = active(run)
    if job is None or (code := exit_code(run, job)) is None:
        return ""
    gone = " (its unit vanished before it recorded an exit: rerun it)" if code == LOST else ""
    out = tail(run, job["id"])
    (run / JOB).unlink(missing_ok=True)
    return f"job {job['id']} ({job['command']}) exited {code}{gone}" + (f"\n{out}" if out else "")


def drop(run: Path) -> None:
    """Forget the card's job and its files (a cancelled run's unit was stopped with the card's slice)."""
    (run / JOB).unlink(missing_ok=True)
    shutil.rmtree(run / DIR, ignore_errors=True)


def arm(run: Path, parser: StreamParser, stop: Callable[[], None]) -> None:
    """End the turn once a `run_job` result is in and no tool call is in flight (the way ctxcap stops one)."""
    before, stopped = parser.on_idle, False

    def idle() -> None:
        nonlocal stopped
        if before is not None:
            before()
        if not stopped and (run / JOB).exists() and not parser.meter.pending:
            stopped = True
            stop()

    parser.on_idle = idle


def wrap(run: Path, build: Callable[[Situation], str]) -> Callable[[Situation], str]:
    """Wrap a prompt builder: a finished job's text is the resumed session's prompt, else added to it."""

    def text_for(situation: Situation) -> str:
        if not (text := take(run)):
            return build(situation)
        return text if situation == "resume" else f"{build(situation)}\n\n{text}"

    return text_for
