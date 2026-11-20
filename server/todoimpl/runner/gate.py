"""The target repo's pre-push gate, run before a ship pushes (T1837).

A repo that carries `scripts/check_gate_stamp.sh` refuses a push whose tree has no gate receipt in `$GIT_DIR`
(`~/.claude/scripts/finish_auto.sh` writes it after its gate). Ship therefore runs the same steps:
`full --list` for the manual-stage hook ids, then `step <id>` for each; the last passing step stamps the
tree. Gates run for minutes, so, like a turn, the gate is its own transient systemd unit (`gatehost`),
never part of the server: a restart or deploy leaves it running and the new server finds its record
`<run dir>/gate/exit.json` (T1817).
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from typing import TYPE_CHECKING

from . import cardslice, launch, stepwatch
from .checks import CheckResult, clean_env, from_row, report
from .files import NeedsYouError, read_json
from .gatehost import STAMP_TOOL
from .worktree import git

if TYPE_CHECKING:
    from pathlib import Path

GATE_DIR = "gate"
EXIT_FILE = "exit.json"
# The unit's RuntimeMaxSec: it may queue behind other gates. The server stops waiting then too.
GATE_TIMEOUT = 14400.0
POLL = 1.0
UNIT_ENV = ("PATH", "HOME", "TODOIMPL_CAPPED", "UTILS_ROOT", "GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
TAIL = 600
_run = subprocess.run  # the one place systemd-run and systemctl are called: tests swap it
SIGNAL_EXITS = (137, 143)  # a shell's report of SIGKILL / SIGTERM; below 0 is Python's own report
WAIT_LINE = "waiting for build lock held by "  # `buildlock.WAITING`: the first line of a queued step
FIX_ASK = "Fix it yourself: commit, rebase, push, deploy (you have permission)."
KILLED_ASK = (
    "The step was killed by a signal twice, most likely the 4 GiB memory cap of capped.sh (OOM): make it "
    "fit, shard it finer or cut its memory (fewer workers or isolates, smaller shards), then commit, rebase, "
    "push, deploy (you have permission)."
)


class GateRedError(NeedsYouError):
    """A pre-push gate step is red; `killed` when a signal ended it (T2340, T2341)."""

    def __init__(self, text: str, step: str, exit_code: int | None, tail: str) -> None:  # noqa: D107
        super().__init__(text, "checks_failed")
        self.step, self.exit_code, self.tail = step, exit_code, tail

    @classmethod
    def build(cls, step: str, exit_code: int | None, tail: str) -> GateRedError:
        """Return the failure of `step` with the text the card shows."""
        code = "timed out" if exit_code is None else f"exit {exit_code}"
        return cls(f"Pre-push gate step {step} is red ({code}):\n{tail[-TAIL:]}", step, exit_code, tail)

    @property
    def killed(self) -> bool:
        """Say whether a signal ended the step (OOM, a stop): not a red test."""
        return self.exit_code is not None and (self.exit_code < 0 or self.exit_code in SIGNAL_EXITS)

    @property
    def waited_only(self) -> bool:
        """Say whether the step was killed before it ran: its log holds nothing but the build lock's wait."""
        lines = [ln for ln in self.tail.splitlines() if ln.strip()]
        return self.killed and bool(lines) and all(ln.startswith(WAIT_LINE) for ln in lines)

    @property
    def output(self) -> str:
        """The brief for the session's fix turn: the step's output, what failed, and what to do."""
        return f"{self.tail[-1800:]}\n\n{self.text}\n\n{KILLED_ASK if self.killed else FIX_ASK}"


def unit_name(card: str) -> str:
    """`todoimpl-gate-<card>`: one gate per card at a time, found again after a restart."""
    return f"todoimpl-gate-{card}"


def host_argv(run_dir: Path, wt: Path) -> list[str]:
    """Return the host's command line: python, not a shell script, so an edit cannot change a live gate."""
    return [sys.executable, "-m", "todoimpl.runner.gatehost", str(run_dir), str(wt)]


def systemd_argv(unit: str, run_dir: Path, wt: Path) -> list[str]:
    """`systemd-run` argv; a transient unit has no server env, so the few vars a gate needs ride as -E."""
    env = clean_env()
    keep = [f"{key}={env[key]}" for key in UNIT_ENV if key in env]
    return [
        "systemd-run", "--user", "--collect", "--quiet", f"--unit={unit}",
        f"--slice={cardslice.card_slice(run_dir.name)}",
        "-p", "KillMode=control-group", "-p", f"RuntimeMaxSec={GATE_TIMEOUT:.0f}",
        "-E", f"PYTHONPATH={launch.SERVER_DIR}", *(arg for kv in keep for arg in ("-E", kv)),
        "--", *host_argv(run_dir, wt),
    ]  # fmt: skip


def _alive(unit: str | None) -> bool:
    """Say whether the unit is running now (systemd only knows it while it runs: `--collect`)."""
    return unit is not None and _run(["systemctl", "--user", "is-active", "--quiet", unit]).returncode == 0


def _start(card: str, run_dir: Path, wt: Path) -> None:
    """Launch the gate host as its own unit (tests: a plain detached child); NeedsYouError if that fails."""
    if launch.direct():
        host = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
            host_argv(run_dir, wt),
            env={**clean_env(), "PYTHONPATH": str(launch.SERVER_DIR)},
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        threading.Thread(target=host.wait, daemon=True).start()
        return
    unit = unit_name(card)
    done = _run(systemd_argv(unit, run_dir, wt), capture_output=True, text=True, check=False)
    if done.returncode != 0:
        msg = f"could not start the gate unit {unit}: {done.stderr.strip()[:300]}"
        raise NeedsYouError(msg)


def _results(steps: list[dict[str, object]]) -> list[CheckResult]:
    return [from_row(s, str(s["name"]), str(s["command"])) for s in steps]


def run(wt: Path, run_dir: Path, card: str) -> list[CheckResult]:
    """Gate HEAD's tree; return one result per step, `[]` for a repo with no stamp tool, raise when red.

    A finished green record for this tree is reused, a unit still running is waited for, otherwise it starts.
    """
    if not (wt / STAMP_TOOL).is_file():
        return []
    tree = git(wt, "rev-parse", "HEAD^{tree}").stdout.strip()
    record = run_dir / GATE_DIR / EXIT_FILE
    unit = unit_name(card)
    deadline = time.monotonic() + GATE_TIMEOUT
    launched = polled = False
    while True:
        stepwatch.relay(run_dir / GATE_DIR / stepwatch.WAIT_FILE)  # the host's queue on the card
        done = read_json(record)
        if isinstance(done, dict) and done.get("tree") == tree and (done.get("ok") or launched):
            break
        if not launched and not _alive(unit):
            record.unlink(missing_ok=True)
            _start(card, run_dir, wt)
            launched = True
        if time.monotonic() > deadline:
            msg = f"The pre-push gate did not report within {GATE_TIMEOUT:g} s: see {run_dir / GATE_DIR}"
            raise NeedsYouError(msg, "checks_failed")
        polled = True
        time.sleep(POLL)
    results = _results(done["steps"])
    if polled:  # not a record reused as it was: the events say how long each step queued and ran
        for result in results:
            report(result)
    red = next((r for r in results if not r.passed), None)
    if red is not None:
        raise GateRedError.build(red.name.removeprefix("gate-"), red.exit_code, red.tail)
    return results
