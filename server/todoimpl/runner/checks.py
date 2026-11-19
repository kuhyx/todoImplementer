"""Run the done_check and the repo's checks through capped.sh with a timeout; keep the tail as evidence."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING, Any

from . import buildlock, checks_guard, lanes, stepwatch
from .claude import kill_tree

if TYPE_CHECKING:
    from collections.abc import Mapping

DEFAULT_TIMEOUT = 600.0
TAIL_LINES = 40
MAKE_TEST = re.compile(r"^test\s*:", re.MULTILINE)
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
SENTENCE_NOTE = "a sentence, not a command: the board does not run it, so cover it with a plan criterion"


@dataclass(frozen=True)
class CheckResult:
    """One check; exit_code None means it timed out. `log` is relative to the run dir."""

    name: str
    command: str
    exit_code: int | None
    tail: str
    log: str
    lane: str = lanes.HEAVY
    queue_s: float = 0.0  # seconds before the lock or slot was this check's (T2185)
    run_s: float = 0.0
    holder: str = ""  # who it queued behind, when it queued

    @property
    def passed(self) -> bool:  # noqa: D102
        return self.exit_code == 0


def clean_env(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return the server's env without its own venv: `VIRTUAL_ENV` and the venv's `bin` on `PATH`.

    A target repo's pre-commit and tools must pick their own python, not the server's (T1836).
    """
    env = dict(os.environ)
    venvs = {env.pop("VIRTUAL_ENV", "")}
    if sys.prefix != sys.base_prefix:
        venvs.add(sys.prefix)
    drop = {f"{v}/bin" for v in venvs if v}
    env["PATH"] = os.pathsep.join(
        p for p in env.get("PATH", "").split(os.pathsep) if p.rstrip("/") not in drop
    )
    return {**env, **(extra or {})}


def capped() -> str:  # noqa: D103
    return os.environ.get("TODOIMPL_CAPPED") or str(Path.home() / ".claude" / "scripts" / "capped.sh")


def is_command(done_check: str, wt: Path) -> bool:
    """Return True when bash parses it and its first word is a builtin, keyword, program or worktree file.

    A done_check written as prose ("a regression test exists under tests/") is a criterion, not a
    command: running it only fails with a syntax error or "command not found" (T1814).
    """
    try:
        words = shlex.split(done_check)
    except ValueError:
        return False
    words = [w for w in words if not ASSIGNMENT.match(w)]
    if not words:
        return False
    parse = ["bash", "-n", "-c", done_check]
    parsed = subprocess.run(parse, capture_output=True, check=False)  # noqa: S603 - only parsed, never run
    if parsed.returncode != 0:
        return False
    first = words[0].lstrip("({")
    if not first or (wt / first).is_file():
        return True
    lookup = ["bash", "-c", 'type -t -- "$1"', "_", first]  # the word is only an argument to `type`
    known = subprocess.run(lookup, cwd=wt, capture_output=True, check=False)  # noqa: S603
    return known.returncode == 0


def shown_done_check(check: str | None, wt: Path) -> str | None:
    """Return the done_check as the prompt shows it: a sentence says the board will not run it."""
    return f"{check} ({SENTENCE_NOTE})" if check and not is_command(check, wt) else check


def discover(wt: Path, done_check: str | None) -> list[tuple[str, str]]:
    """List the note's done_check (when it is a command) first, then `make test` and pre-commit."""
    found = [("done_check", done_check)] if done_check and is_command(done_check, wt) else []
    makefile = wt / "Makefile"
    if makefile.exists() and MAKE_TEST.search(makefile.read_text(encoding="utf-8", errors="replace")):
        found.append(("tests", "make test"))
    if (wt / ".pre-commit-config.yaml").exists():
        found.append(("pre-commit", "pre-commit run --all-files"))
    return found


def pool_env(run_dir: Path) -> dict[str, str]:
    """capped.sh pools scopes per CLAUDE_CODE_SESSION_ID: give each run's checks a pool of their own.

    Without it every run's checks shared one 4 GiB `capped-nosession` pool, and a sibling run's
    build filling it got this run's astro build OOM-killed mid pre-commit (exit -15, 2026-11-11).
    The machine-wide capped.slice backstop still bounds all runs together.
    """
    return {"CLAUDE_CODE_SESSION_ID": "todoimpl" + re.sub(r"[^A-Za-z0-9]", "", run_dir.name)}


def run_capped(  # noqa: PLR0913 - guard and timing are keyword-only
    command: str,
    cwd: Path,
    timeout: float,
    out: IO[str] | int = subprocess.DEVNULL,
    env: Mapping[str, str] | None = None,
    *,
    guard: Path | None = None,
    timing: lanes.Timing | None = None,
) -> int | None:
    """`capped.sh bash -c command` in its own process group; None when it timed out (the tree is killed).

    `guard` is a run dir: the group is recorded there while it runs, so a later server can stop it (T1889).
    A build first waits for the machine-wide build lock (buildlock.py), a linter for the light slot
    (lanes.py), both outside the timeout; `timing` gets the lane and the queue and run seconds (T2185).
    """
    with lanes.admitted(command, cwd, guard.name if guard else "board", out, timing):
        proc = subprocess.Popen(  # noqa: S603 - argv list; the command is the note's own (trusted) done_check
            [capped(), "bash", "-c", command],
            cwd=cwd,
            env=clean_env({**(env or {}), buildlock.HELD_VAR: "1"}),
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if guard is not None:
            checks_guard.remember(guard, proc.pid)
        try:
            return proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc, grace=1.0)
            return None
        finally:
            if guard is not None:
                checks_guard.forget(guard, proc.pid)


def run_check(  # noqa: PLR0913, PLR0917 - one knob (env) more than the lint allows
    name: str,
    command: str,
    cwd: Path,
    run_dir: Path,
    timeout: float = DEFAULT_TIMEOUT,
    env: Mapping[str, str] | None = None,
) -> CheckResult:
    """Run one check in its own process group (a timeout kills the whole tree); log to evidence/.

    `env` adds to the server's env minus its venv (e.g. a higher `CAP_MEM` for the capped.sh scope).
    """
    log = run_dir / "evidence" / f"check-{name}-{time.time():.3f}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    checks_guard.stop_stale(run_dir)  # a dead server's run of this check would clash with this one (T1889)
    timing = lanes.Timing()
    with log.open("w", encoding="utf-8") as out:
        env_all = {**pool_env(run_dir), **(env or {})}
        code = run_capped(command, cwd, timeout, out, env_all, guard=run_dir, timing=timing)
        if code is None:
            out.write(f"\n[timed out after {timeout:g} s]\n")
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    result = CheckResult(
        name, command, code, "\n".join(lines[-TAIL_LINES:]).strip(), str(log.relative_to(run_dir)),
        timing.lane, timing.queue_s, timing.run_s, timing.holder,
    )  # fmt: skip
    report(result)
    return result


def report(result: CheckResult) -> None:
    """Write the event line of a finished check, its lane and its queue and run seconds apart (T2185).

    A gate or deploy step runs in a host process with no card: the server reports it from the host's record.
    """
    if (watch := stepwatch.current()) is not None:
        code = "timeout" if result.exit_code is None else result.exit_code
        behind = f" behind={result.holder}" if result.holder else ""
        watch.say(
            f"check {result.name}: lane={result.lane} queue={result.queue_s:.1f}s run={result.run_s:.1f}s"
            f" exit={code}{behind}"
        )


def timing_row(result: CheckResult) -> dict[str, object]:
    """Return a result's timing as a host's record keeps it; `from_row` reads it back."""
    return {"lane": result.lane, "queue_s": result.queue_s, "run_s": result.run_s, "holder": result.holder}


def from_row(row: Mapping[str, Any], name: str, command: str) -> CheckResult:
    """Return the result a host's record row describes (rows of an older host have no timing)."""
    return CheckResult(
        name, command, row["exit"], str(row["tail"]), str(row["log"]), str(row.get("lane", lanes.HEAVY)),
        float(row.get("queue_s", 0.0)), float(row.get("run_s", 0.0)), str(row.get("holder", "")),
    )  # fmt: skip


def run_all(
    checks: list[tuple[str, str]], cwd: Path, run_dir: Path, timeout: float = DEFAULT_TIMEOUT
) -> tuple[list[CheckResult], str]:
    """Run every check (no early stop, so the evidence is complete) and write `logs/checks-<epoch>.log`."""
    results = [run_check(name, command, cwd, run_dir, timeout) for name, command in checks]
    body = "\n\n".join(f"== {r.name}: {r.command} -> {r.exit_code}\n{r.tail}" for r in results)
    log = run_dir / "logs" / f"checks-{time.time():.3f}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text((body or "no checks found") + "\n", encoding="utf-8")
    return results, str(log.relative_to(run_dir))


def record(results: list[CheckResult], log: str, now: float) -> dict[str, Any]:
    """Return the state.json `checks` object; a timed-out check is recorded with exit -1."""
    rows = [
        {"command": r.command, "exit": -1 if r.exit_code is None else r.exit_code, "tail": r.tail}
        for r in results
    ]
    return {"passed": all(r.passed for r in results), "ran_at": now, "log": log, "results": rows}
