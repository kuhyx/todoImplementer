"""The board runs the repo's gate before a card ships, as a job: the session never runs the suite.

The command is the worktree's CLAUDE.md `- gate:` bullet, else its `- test:` bullet
(`nolimit.repos.commands_of`); a repo with neither is checked as before (`checks.discover`). It runs as a
`run_job` unit (`jobs.py`: unit in the card's slice, `<run>/jobs/<id>.out`, exit record), so a server restart
finds it again. Green goes on to Ship. Red resumes the session ONCE: the job's resume text (exit code, last 40
lines) is the fix turn's failure tail, and the fix returns to the checks; a second red is Needs you like red
checks (`checks_failed`). A job a signal ended, or whose unit vanished, is rerun without counting (`KILLS`).
All of it lives in one `extra` key, `gate_job`: `{"fixes": n, "kills": n, "again": bool}`.
"""

from __future__ import annotations

import shlex
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.nolimit.repos import claude_md, commands_of
from todoimpl.peer.limits import Refusal
from todoimpl.umbrella import bounce

from . import checks, checksteps, jobs, launch
from .files import NeedsYouError
from .jobwait import POLL, hold

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .pipeline import Driver

NAME = "gate"  # the job's name: the card shows `job gate`, a restart adopts it
KEY = "gate_job"
MAX_FIXES = 1  # fix turns a red gate gets; the next red is Needs you
KILLS = 2  # reruns of a gate its signal or vanished unit ended
KILLED = (137, 143, jobs.LOST)
TIMEOUT = 14400.0  # seconds a gate may run, as the pre-push gate (`gate.GATE_TIMEOUT`)


def mem(st: RunState) -> dict[str, Any]:
    """Return the run's gate record (`fixes`, `kills`, `again`), created on first use."""
    rec: dict[str, Any] = st.extra.setdefault(KEY, {})
    return rec


def command(wt: Path) -> str | None:
    """Return the repo's gate (`gate:` bullet, else `test:`) from CLAUDE.md in `wt`; None without either."""
    found = commands_of(claude_md(wt))
    return found.get("gate") or found.get("test")


def job_command(gate: str, wt: Path, run_dir: Path) -> str:
    """Return the job's shell line: the gate's steps (a sharded `make test` as its shards) under capped.sh."""
    steps = checksteps.steps(gate, wt, run_dir / "gate-cov")
    pool = " ".join(f"{k}={shlex.quote(v)}" for k, v in checks.pool_env(run_dir).items())
    return f"{pool} {shlex.quote(checks.capped())} bash -c {shlex.quote(' && '.join(steps))}"


def _run(d: Driver, gate: str) -> tuple[int, str]:
    """Run (or adopt) the card's gate job; return its exit code and resume text, the job record consumed."""
    run, st = d.ctx.run_dir, d.state
    job = jobs.active(run)
    if job is None or job.get("name") != NAME:
        d.save()  # `jobs.start` reads the state from disk
        try:
            jobs.start(d.ctx.root, run.name, job_command(gate, Path(str(st.worktree)), run), NAME)
        except Refusal as refused:
            msg = f"The gate job did not start: {refused}"
            raise NeedsYouError(msg, "checks_failed") from refused
        job = jobs.active(run)
    if job is None:
        msg = "The gate job left no record."
        raise NeedsYouError(msg, "checks_failed")
    deadline = time.monotonic() + TIMEOUT

    def tick(seconds: float) -> None:
        if time.monotonic() > deadline:
            launch.stop_unit(job.get("unit"))
            jobs.drop(run)
            msg = f"The gate job did not end within {TIMEOUT:g} s."
            raise NeedsYouError(msg, "checks_failed")
        time.sleep(seconds)

    hold(d, tick)  # returns at once when a turn is still on record: the loop below waits then
    while (code := jobs.exit_code(run, job)) is None:
        tick(POLL)
    return code, jobs.take(run)


def run(d: Driver) -> str | None:
    """Run the repo's gate; None when green or absent, else the red job's resume text."""
    st = d.state
    if (gate := command(Path(str(st.worktree)))) is None:
        return None
    while True:
        d.activity(f"gate: {gate}")
        code, text = _run(d, gate)
        if code in KILLED and (kills := int(mem(st).get("kills", 0))) < KILLS:
            mem(st)["kills"] = kills + 1
            d.activity(f"gate job ended by a signal (exit {code}): rerun {kills + 1}/{KILLS}")
            continue
        mem(st).pop("kills", None)
        d.activity("gate: green" if code == 0 else f"gate: exit {code}")
        return None if code == 0 else text


def settle(d: Driver) -> str | None:
    """Run the gate; return None to ship on, `implement` for the one fix turn; red again is Needs you."""
    st = d.state
    if (text := run(d)) is None:
        st.extra.pop(KEY, None)
        return None
    fixes, cap = int(mem(st).get("fixes", 0)), bounce.check_cap(st, MAX_FIXES)
    if fixes >= cap:
        msg = f"The gate is still red after {cap} fix turn(s):\n{text[-600:]}"
        raise NeedsYouError(msg, "checks_failed")
    mem(st).update(fixes=fixes + 1, again=True)
    st.extra["failure_tail"] = bounce.red_tail(st, text)
    return "implement"


def again(st: RunState) -> bool:
    """Say whether the session is on the fix turn of a red gate (its `D:` goes back to the checks)."""
    return bool(st.extra.get(KEY, {}).get("again"))
