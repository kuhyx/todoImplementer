"""Run the done_check and the repo's checks through capped.sh with a timeout; keep the tail as evidence."""

from __future__ import annotations

import os
import re
import shlex
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .claude import kill_tree

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

    @property
    def passed(self) -> bool:  # noqa: D102
        return self.exit_code == 0


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


def run_check(
    name: str, command: str, cwd: Path, run_dir: Path, timeout: float = DEFAULT_TIMEOUT
) -> CheckResult:
    """Run one check in its own process group (a timeout kills the whole tree); log to evidence/."""
    log = run_dir / "evidence" / f"check-{name}-{time.time():.3f}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("w", encoding="utf-8") as out:
        proc = subprocess.Popen(  # noqa: S603 - argv list; the command is the note's own done_check
            [capped(), "bash", "-c", command],
            cwd=cwd,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        code: int | None
        try:
            code = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            kill_tree(proc, grace=1.0)
            code = None
            out.write(f"\n[timed out after {timeout:g} s]\n")
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    return CheckResult(
        name, command, code, "\n".join(lines[-TAIL_LINES:]).strip(), str(log.relative_to(run_dir))
    )


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
