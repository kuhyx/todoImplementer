"""Deploy what a ship pushed, before the note closes (kuhy, 2026-11-11: done means deployed).

A repo declares its deploy in CLAUDE.md, Commands section, as a bullet: ``- deploy: `<command>` ``. The server
reads it from the worktree's HEAD (the pushed commit), never from kuhy's checkout. Like the pre-push gate, the
deploy is its own transient systemd unit (`deployhost`): it takes minutes (APK builds) and a repo's own deploy
may restart this server. The server waits for `<run dir>/deploy/exit.json`; a run found again after a restart
finds the unit still running, or its record, and goes on from there (`run`). Every failure here is a
`NeedsYouError` starting "pushed, not deployed": the code is on origin, the note stays open.
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from dataclasses import asdict, replace
from typing import TYPE_CHECKING, Any

from . import cardslice, deployheal, launch, srcguard, stepwatch, stray
from .checks import CheckResult, clean_env, from_row, report
from .deployheal import DirtyCheckoutError
from .deployhost import DEPLOY_DIR, EXIT_FILE
from .deployline import PREFIX, command_of, is_none, nothing
from .files import NeedsYouError, read_json, root_of, write_json
from .gate import UNIT_ENV, WAIT_LINE
from .worktree import git, repo_dir

if TYPE_CHECKING:
    from pathlib import Path

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
_run = subprocess.run  # the one place systemd-run and systemctl are called: tests swap it


class DeployFailedError(NeedsYouError):
    """The deploy command ran and failed; `exit_code` is its exit status (None: it timed out)."""

    def __init__(self, text: str, exit_code: int | None, tail: str = "") -> None:  # noqa: D107
        super().__init__(text, "run_failed")
        self.exit_code = exit_code
        self.tail = tail

    @classmethod
    def build(cls, exit_code: int | None, tail: str) -> DeployFailedError:
        """Return the failure; its text leads with the FAIL lines the shown tail would cut (T2050).

        The build lock's wait line is no cause: the text leaves it out, the brief keeps it (T2508).
        """
        why = "timed out" if exit_code is None else f"exit {exit_code}"
        shown = "\n".join(ln for ln in tail.splitlines() if not ln.startswith(WAIT_LINE)).strip()
        cut = [ln.strip()[:FAIL_WIDTH] for ln in shown[:-TAIL].splitlines() if "FAIL" in ln]
        lead = f"{' | '.join(cut[:FAIL_LINES])} ... " if cut else ""
        return cls(f"{PREFIX}: deploy failed ({why}): {lead}{shown[-TAIL:]}", exit_code, tail)

    @property
    def output(self) -> str:
        """The brief for the session's fix turn: what the deploy printed and what to do about it."""
        return f"{self.text}\n\n{self.tail[-FIX_TAIL:]}\n\n{FIX_ASK}"


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
        f"--slice={cardslice.card_slice(run_dir.name)}",
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


def _heal(repo: str | None, tail: str, run_dir: Path, notes: list[str], *, healed: bool) -> bool:
    """Say whether to deploy once more: the blocking edits equalled the incoming files, or were set aside.

    Edits at rest for `deployheal.QUIET` s, or a card's recorded ones at once (T2518), are strays (T2512):
    stashed, a patch in the run dir, a line in `notes`. Raises DirtyCheckoutError for fresh edits (the
    checkout stays as is); False when there is no checkout (T2007), or the deploy refused a dirty tree but
    it is clean (T2507).
    """
    try:
        checkout = repo_dir(repo)
    except NeedsYouError:
        return False
    files: list[str] = []
    if not healed:
        try:
            if deployheal.BLOCKED not in tail and not deployheal.dirty(checkout):
                return False
            files, blocking = deployheal.heal(checkout, every=deployheal.BLOCKED not in tail)
        except NeedsYouError:  # git failed there (a lock of kuhy's own git): wait, as for his edits
            files = deployheal.listed(tail)
        else:
            if not files:
                return True
            owner = srcguard.owner(root_of(run_dir), checkout, blocking) or ""  # a card's edits: no wait
            if aside := deployheal.set_aside(
                checkout, blocking, run_dir / DEPLOY_DIR, run_dir.name, time.time(), owner
            ):  # every blocking file, equal ones too (T2518); work origin lacks: a ticket for Claude (T2514)
                notes.append(stray.route(checkout, str(repo), aside, blocking, time.time()))
                return True
    raise DirtyCheckoutError(PREFIX, checkout, files or deployheal.listed(tail), run_dir.name)


def run(wt: Path, run_dir: Path, card: str, repo: str | None, command: str | None = None) -> CheckResult:
    """Deploy HEAD with `command` (default: the one CLAUDE.md declares); return the passing result.

    Raises "pushed, not deployed" when nothing is declared, the deploy fails or times out, or never reports.
    A pull that git stops on kuhy's edits in his checkout is `DirtyCheckoutError` (see `deployheal`).
    """
    command = command or command_of(wt, repo)
    if is_none(command):  # `- deploy: none (<why>)`: nothing runs anywhere, the push is the deploy (T2342)
        return nothing(command)
    commit = git(wt, "rev-parse", "HEAD").stdout.strip()
    healed, notes = False, list[str]()
    while True:
        done = _record(run_dir, commit, command, card, wt)
        git(
            wt, "reset", "--hard", "--quiet", "HEAD", check=False
        )  # what the deploy left in the tree is not work:
        git(wt, "clean", "-fdq", check=False)  # a later squash (`add --all`) must not push it
        result = CheckResult("deploy", command, done["exit"], str(done["tail"]), str(done["log"]))
        if result.passed:  # the close evidence names any stray edits the board set aside
            return replace(result, tail="\n".join([result.tail, *notes])) if notes else result
        if deployheal.blocked(result.tail) and _heal(repo, result.tail, run_dir, notes, healed=healed):
            healed = True
            continue
        raise DeployFailedError.build(result.exit_code, result.tail)
