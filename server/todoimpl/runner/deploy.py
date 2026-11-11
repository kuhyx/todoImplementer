"""Deploy what a ship pushed, before the note closes (kuhy, 2026-11-11: done means deployed).

A repo declares its deploy in CLAUDE.md, Commands section, as a bullet: ``- deploy: `<command>` ``. The server
reads it from the worktree's HEAD (the pushed commit), never from kuhy's checkout. Like the pre-push gate, the
deploy is its own transient systemd unit (`deployhost`): it takes minutes (APK builds) and a repo's own deploy
may restart this server. The server waits for `<run dir>/deploy/exit.json`; a run found again after a restart
finds the unit still running, or its record, and goes on from there (`run`). Every failure here is a
`NeedsYouError` starting "pushed, not deployed": the code is on origin, the note stays open.
"""

from __future__ import annotations

import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from . import launch
from .checks import CheckResult, clean_env
from .deployhost import DEPLOY_DIR, EXIT_FILE
from .files import NeedsYouError, read_json, write_json
from .gate import UNIT_ENV
from .worktree import git

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = "pushed, not deployed"  # what every failure here starts with: the umbrella card keys on it
PUSHED = "pushed.json"  # the run's own push: commit, time, the checks that were green for it
UNIT_MAX = 14400.0  # the unit's RuntimeMaxSec: it may queue behind gates; above deployhost.TIMEOUT
WAIT = UNIT_MAX + 120.0  # the server stops waiting once the unit cannot be running any more
POLL = 1.0
TAIL = 600
LINE = re.compile(r"^[ \t]*[-*][ \t]+deploy:[ \t]*`([^`\n]+)`", re.IGNORECASE)
FENCE = re.compile(r"^[ \t]*(```|~~~)")
_run = subprocess.run  # the one place systemd-run and systemctl are called: tests swap it


def declared(text: str) -> str | None:
    """Return the command of the first `- deploy: `<command>`` bullet outside code fences, else None."""
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (found := LINE.match(line)) and found.group(1).strip():
            return found.group(1).strip()
    return None


def command_of(wt: Path, repo: str | None) -> str:
    """Return the deploy command CLAUDE.md declares at HEAD, or raise "pushed, not deployed"."""
    shown = git(wt, "show", "HEAD:CLAUDE.md", check=False)
    if (command := declared(shown.stdout) if shown.returncode == 0 else None) is None:
        msg = f"{PREFIX}: {repo or 'the repo'} declares no deploy: command in CLAUDE.md"
        raise NeedsYouError(msg, "run_failed")
    return command


def mark_pushed(run_dir: Path, commit: str, at: float, results: list[CheckResult]) -> None:
    """Record this run's own push: a Retry or a restart then never pushes (or squashes) again."""
    write_json(run_dir / PUSHED, {"commit": commit, "pushed_at": at, "results": [asdict(r) for r in results]})


def forget(run_dir: Path) -> None:
    """Drop the push record: work may follow it, so it no longer fits the worktree (any drive but Ship)."""
    (run_dir / PUSHED).unlink(missing_ok=True)


def pushed(run_dir: Path, wt: Path) -> dict[str, Any] | None:
    """Return the push record when it names the worktree's HEAD (the checks were green for it), else None."""
    record = read_json(run_dir / PUSHED)
    if not isinstance(record, dict) or not wt.is_dir():
        return None
    return (
        record if record.get("commit") == git(wt, "rev-parse", "HEAD", check=False).stdout.strip() else None
    )


def unit_name(card: str) -> str:
    """`todoimpl-deploy-<card>`: one deploy per card at a time, found again after a restart."""
    return f"todoimpl-deploy-{card}"


def host_argv(run_dir: Path, wt: Path, command: str) -> list[str]:
    """Return the host's command line: python, not a shell script, so an edit cannot change a live deploy."""
    return [sys.executable, "-m", "todoimpl.runner.deployhost", str(run_dir), str(wt), command]


def systemd_argv(unit: str, run_dir: Path, wt: Path, command: str) -> list[str]:
    """`systemd-run` argv; a transient unit has no server env, so the few vars a deploy needs ride as -E."""
    env = clean_env()
    keep = [f"{key}={env[key]}" for key in UNIT_ENV if key in env]
    return [
        "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
        "-p", "KillMode=control-group", "-p", f"RuntimeMaxSec={UNIT_MAX:.0f}",
        "-E", f"PYTHONPATH={launch.SERVER_DIR}", *(arg for kv in keep for arg in ("-E", kv)),
        "--", *host_argv(run_dir, wt, command),
    ]  # fmt: skip


def _alive(unit: str | None) -> bool:
    """Say whether the unit is running now (systemd only knows it while it runs: `--collect`)."""
    return unit is not None and _run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0


def _start(card: str, run_dir: Path, wt: Path, command: str) -> None:
    """Launch the deploy host as its own unit (tests: a plain detached child); NeedsYouError if that fails."""
    if launch.direct():
        host = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            host_argv(run_dir, wt, command),
            env={**clean_env(), "PYTHONPATH": str(launch.SERVER_DIR)},
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=host.wait, daemon=True).start()
        return
    unit = unit_name(card)
    done = _run(systemd_argv(unit, run_dir, wt, command), capture_output=True, text=True, check=False)
    if done.returncode != 0:
        msg = f"{PREFIX}: could not start the deploy unit {unit}: {done.stderr.strip()[:300]}"
        raise NeedsYouError(msg, "run_failed")


def _record(run_dir: Path, commit: str, command: str, card: str, wt: Path) -> dict[str, Any]:
    """Wait for the deploy of `commit`: reuse a green record, wait for a running unit, else start one."""
    record = run_dir / DEPLOY_DIR / EXIT_FILE
    unit, launched = unit_name(card), False
    deadline = time.monotonic() + WAIT
    while True:
        done = read_json(record)
        if isinstance(done, dict) and done.get("commit") == commit and (done.get("ok") or launched):
            return done
        if not launched and not _alive(unit):
            record.unlink(missing_ok=True)
            _start(card, run_dir, wt, command)
            launched = True
        if time.monotonic() > deadline:
            msg = f"{PREFIX}: the deploy did not report within {WAIT:g} s: see {run_dir / DEPLOY_DIR}"
            raise NeedsYouError(msg, "run_failed")
        time.sleep(POLL)


def run(wt: Path, run_dir: Path, card: str, repo: str | None, command: str | None = None) -> CheckResult:
    """Deploy HEAD with `command` (default: the one CLAUDE.md declares); return the passing result.

    Raises "pushed, not deployed" when nothing is declared, the deploy fails or times out, or never reports.
    """
    command = command or command_of(wt, repo)
    commit = git(wt, "rev-parse", "HEAD").stdout.strip()
    done = _record(run_dir, commit, command, card, wt)
    git(
        wt, "reset", "--hard", "--quiet", "HEAD", check=False
    )  # what the deploy left in the tree is not work:
    git(wt, "clean", "-fdq", check=False)  # a later squash (`add --all`) must not push it
    result = CheckResult("deploy", command, done["exit"], str(done["tail"]), str(done["log"]))
    if not result.passed:
        why = "timed out" if result.exit_code is None else f"exit {result.exit_code}"
        msg = f"{PREFIX}: deploy failed ({why}): {result.tail[-TAIL:]}"
        raise NeedsYouError(msg, "run_failed")
    return result
