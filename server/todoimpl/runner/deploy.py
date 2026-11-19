"""Deploy what a ship pushed, before the note closes (kuhy, 2026-11-11: done means deployed).

A repo declares its deploy in CLAUDE.md, Commands section, as a bullet: ``- deploy: `<command>` ``. The server
reads it from the worktree's HEAD (the pushed commit), never from kuhy's checkout. Like the pre-push gate, the
deploy is its own transient systemd unit (`deployhost`): it takes minutes (APK builds) and a repo's own deploy
may restart this server. The server waits for `<run dir>/deploy/exit.json`; a run found again after a restart
finds the unit still running, or its record, and goes on from there (`run`). Every failure here is a
`NeedsYouError` starting "pushed, not deployed": the code is on origin, the note stays open.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from . import deployheal, launch, stepwatch
from .checks import CheckResult, clean_env, from_row, report
from .deployheal import DirtyCheckoutError
from .deployhost import DEPLOY_DIR, EXIT_FILE
from .files import NeedsYouError, read_json, write_json
from .gate import UNIT_ENV
from .worktree import git, repo_dir

if TYPE_CHECKING:
    from pathlib import Path

PREFIX = "pushed, not deployed"  # what every failure here starts with: the umbrella card keys on it
PUSHED = "pushed.json"  # the run's own push: commit, time, the checks that were green for it
UNIT_MAX = 14400.0  # the unit's RuntimeMaxSec: it may queue behind gates; above deployhost.TIMEOUT
WAIT = UNIT_MAX + 120.0  # the server stops waiting once the unit cannot be running any more
POLL = 1.0
TAIL = 600
FIX_TAIL = 1800  # of the deploy output the fix turn is briefed with
FAIL_LINES, FAIL_WIDTH = (
    3,
    200,
)  # the deploy's own FAIL lines that lead the text when the shown tail cuts them
FIX_ASK = (
    "Fix it yourself: bump and tag the changed package, push, redeploy, read the result "
    "(you have permission; a check like 'X changed after <tag>' wants a version bump and a release)."
)
LINE = re.compile(r"^[ \t]*[-*][ \t]+deploy:[ \t]*`([^`\n]+)`", re.IGNORECASE)
LINK_HOPS = 5  # CLAUDE.md -> AGENTS.md is one hop; a few more cover a chain, a loop ends here
SYMLINK_MODE = "120000"  # git tree mode of a symlink
LS_FIELDS = 4  # `git ls-tree` prints <mode> <type> <sha>\t<path>
FENCE = re.compile(r"^[ \t]*(```|~~~)")
_run = subprocess.run  # the one place systemd-run and systemctl are called: tests swap it


class DeployFailedError(NeedsYouError):
    """The deploy command ran and failed; `exit_code` is its exit status (None: it timed out)."""

    def __init__(self, text: str, exit_code: int | None, tail: str = "") -> None:  # noqa: D107
        super().__init__(text, "run_failed")
        self.exit_code = exit_code
        self.tail = tail

    @classmethod
    def build(cls, exit_code: int | None, tail: str) -> DeployFailedError:
        """Return the failure; its text leads with the FAIL lines the shown tail would cut (T2050)."""
        why = "timed out" if exit_code is None else f"exit {exit_code}"
        cut = [ln.strip()[:FAIL_WIDTH] for ln in tail[:-TAIL].splitlines() if "FAIL" in ln]
        lead = f"{' | '.join(cut[:FAIL_LINES])} ... " if cut else ""
        return cls(f"{PREFIX}: deploy failed ({why}): {lead}{tail[-TAIL:]}", exit_code, tail)

    @property
    def output(self) -> str:
        """The brief for the session's fix turn: what the deploy printed and what to do about it."""
        return f"{self.text}\n\n{self.tail[-FIX_TAIL:]}\n\n{FIX_ASK}"


def declared(text: str) -> str | None:
    """Return the command of the first `- deploy: `<command>`` bullet outside code fences, else None."""
    fenced = False
    for line in text.splitlines():
        if FENCE.match(line):
            fenced = not fenced
        elif not fenced and (found := LINE.match(line)) and found.group(1).strip():
            return found.group(1).strip()
    return None


def claude_md(wt: Path) -> str:
    """Return CLAUDE.md as committed at HEAD, following in-repo symlinks (CLAUDE.md -> AGENTS.md), else "".

    `git show` on a symlink returns the link text, so the blob is resolved by hand: a target that is absolute,
    leaves the repo, dangles, is not a file or loops past `LINK_HOPS` yields "".
    """
    path = "CLAUDE.md"
    for _ in range(LINK_HOPS):
        entry = git(wt, "ls-tree", "HEAD", "--", path, check=False).stdout.split(maxsplit=3)
        if len(entry) < LS_FIELDS or entry[1] != "blob":
            return ""
        blob = git(wt, "cat-file", "blob", entry[2], check=False).stdout
        if entry[0] != SYMLINK_MODE:
            return blob
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), blob.strip()))
        if blob.startswith("/") or target == ".." or target.startswith("../"):
            return ""
        path = target
    return ""


def command_of(wt: Path, repo: str | None) -> str:
    """Return the deploy command CLAUDE.md declares at HEAD, or raise "pushed, not deployed"."""
    if (command := declared(claude_md(wt))) is None:
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
        "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}", f"--slice={launch.SLICE}",
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
        stepwatch.relay(run_dir / DEPLOY_DIR / stepwatch.WAIT_FILE)  # the host's queue on the card
        done = read_json(record)
        if isinstance(done, dict) and done.get("commit") == commit and (done.get("ok") or launched):
            if launched:  # not a green record reused: the events say how long it queued and ran
                report(from_row(done, "deploy", command))
            return done
        if not launched and not _alive(unit):
            record.unlink(missing_ok=True)
            _start(card, run_dir, wt, command)
            launched = True
        if time.monotonic() > deadline:
            msg = f"{PREFIX}: the deploy did not report within {WAIT:g} s: see {run_dir / DEPLOY_DIR}"
            raise NeedsYouError(msg, "run_failed")
        time.sleep(POLL)


def _heal(repo: str | None, tail: str, *, healed: bool) -> bool:
    """Say whether to deploy once more: kuhy's blocking edits equalled the incoming files and are restored.

    Raises DirtyCheckoutError when his own edits block the pull (the checkout is left as it is); False when
    there is no checkout to look at (T2007).
    """
    try:
        checkout = repo_dir(repo)
    except NeedsYouError:
        return False
    files: list[str] = []
    if not healed:
        try:
            files = deployheal.heal(checkout)
        except NeedsYouError:  # git failed there (a lock of kuhy's own git): wait, as for his edits
            files = deployheal.listed(tail)
        else:
            if not files:
                return True
    raise DirtyCheckoutError(PREFIX, checkout, files or deployheal.listed(tail))


def run(wt: Path, run_dir: Path, card: str, repo: str | None, command: str | None = None) -> CheckResult:
    """Deploy HEAD with `command` (default: the one CLAUDE.md declares); return the passing result.

    Raises "pushed, not deployed" when nothing is declared, the deploy fails or times out, or never reports.
    A pull that git stops on kuhy's edits in his checkout is `DirtyCheckoutError` (see `deployheal`).
    """
    command = command or command_of(wt, repo)
    commit = git(wt, "rev-parse", "HEAD").stdout.strip()
    healed = False
    while True:
        done = _record(run_dir, commit, command, card, wt)
        git(
            wt, "reset", "--hard", "--quiet", "HEAD", check=False
        )  # what the deploy left in the tree is not work:
        git(wt, "clean", "-fdq", check=False)  # a later squash (`add --all`) must not push it
        result = CheckResult("deploy", command, done["exit"], str(done["tail"]), str(done["log"]))
        if result.passed:
            return result
        if deployheal.blocked(result.tail) and _heal(repo, result.tail, healed=healed):
            healed = True
            continue
        raise DeployFailedError.build(result.exit_code, result.tail)
