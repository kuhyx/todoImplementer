"""Run the done_check and the repo's checks through capped.sh with a timeout; keep the tail as evidence."""

from __future__ import annotations

import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .claude import kill_tree

DEFAULT_TIMEOUT = 600.0
TAIL_LINES = 40
MAKE_TEST = re.compile(r"^test\s*:", re.MULTILINE)


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


def discover(wt: Path, done_check: str | None) -> list[tuple[str, str]]:
    """List the note's done_check first, then `make test` and pre-commit when the repo has them."""
    found = [("done_check", done_check)] if done_check else []
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
