"""The one way a free worker is launched: `python -m todoimpl.runner.freeworker <worktree> <prompt> <log>`.

Raw `claude-free -p <task>` loads kuhy's whole ~/.claude, whose spec gate answers a fully specified task
with a grilling round (the `\u2753` question card) and no edit (smoke test 2026-11-10). This wrapper runs it
with the board's hooks-off settings and a fixed no-questions preamble, under `srcwall` (kuhy's checkouts
read-only, T2519), writes stdout and stderr to the log,
and judges success by the worktree diff, never by the turn's `subtype: success`. A turn that ends with no
diff and a grilling round is written to the issue log (`--issues <run dir>`, umbrella/issues.py).
Exit 0 = the worktree changed; 3 = no work; 4 = no `claude-free`; 5 = killed by a signal on every attempt.
"""

from __future__ import annotations

import argparse
import functools
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

from todoimpl.board.clone import src_root
from todoimpl.umbrella import issues, workers

from . import srcguard, srcwall, workerwait
from .claude import SETTING_SOURCES, TOOLS
from .policy import HOOKS_OFF, src_deny

PREAMBLE = (
    "You are a non-interactive worker. The task is fully specified and approved by kuhy: never ask "
    "questions, never run a spec gate or grilling round; make the edits now."
)
DENY = ("Bash(git push:*)", "Bash(git push *)")  # only Ship pushes
SCOPE = (
    "Your worktree is {worktree}. Edit files only under it: kuhy's own checkouts under {src} are off-limits, "
    "by shell too (no cd, cp, sed, git or pub get there; other repos have their own parts; a task that says "
    "everywhere means this repo only)."
)
GRILL = "❓"
GRILLING = "spec-gate grilling instead of work"
TIMEOUT = 3600.0
TAIL = 500
NOISE = ("⚠", "Warning:", "[claude-code:", "Claude Code doesn't recognize")  # startup lines, not the answer
MODEL = re.compile(r'"model":"([^"]+)"')
NO_WORK, NO_TOOL, KILLED = 3, 4, 5
TIMED_OUT = 124  # the coreutils `timeout` convention
SIGNAL_EXIT = 128
MAX_ATTEMPTS = 3
PAUSE = 5.0  # seconds before the next attempt after a kill, times the attempt number


def command() -> str:
    """Return the shell prefix prompts hand to a manager: python with this package on its path."""
    return f"PYTHONPATH={Path(__file__).resolve().parents[2]} {sys.executable} -m todoimpl.runner.freeworker"


def _git(worktree: Path, *args: str) -> str:
    done = subprocess.run(  # noqa: S603 - fixed argv, no shell
        ["git", *args],  # noqa: S607
        cwd=worktree, capture_output=True, text=True, check=False,
    )  # fmt: skip
    return done.stdout.strip()


def _state(worktree: Path) -> tuple[str, str]:
    """Return (HEAD, porcelain status): a change in either is work."""
    return _git(worktree, "rev-parse", "HEAD"), _git(worktree, "status", "--porcelain")


def _killed(code: int) -> bool:
    """Say whether a signal ended the worker: Python reports -N, a shell wrapper 128 + N."""
    return code < 0 or code >= SIGNAL_EXIT


def _attempt(argv: list[str], worktree: Path, log: Path) -> int:
    with log.open("a", encoding="utf-8") as out:
        try:
            return subprocess.run(  # noqa: S603 - argv list, no shell
                argv, cwd=worktree, stdout=out, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                timeout=TIMEOUT, check=False,
            ).returncode  # fmt: skip
        except subprocess.TimeoutExpired:
            out.write(f"\n[timed out after {TIMEOUT:g} s]\n")
            return TIMED_OUT


def run(worktree: Path, prompt_file: Path, log: Path, *, run_dir: Path | None = None, child: str = "") -> int:
    """Run one worker; `run_dir` holds free-issues.jsonl, `child` names the repo. Return the exit code.

    A worker killed by a signal (OOM, SIGKILL) is logged as phase `killed` and started again, up to
    MAX_ATTEMPTS times; one that is killed every time exits KILLED whatever it left in the tree.
    """
    tool = shutil.which("claude-free")
    if tool is None:
        _issue(run_dir, child, "start", "claude-free is not installed")
        return NO_TOOL
    before = _state(worktree)
    src = src_root()
    scope = SCOPE.format(worktree=worktree, src=src)
    task = prompt_file.read_text(encoding="utf-8")
    wall, unguarded = srcwall.wrap(worktree, src)  # T2519: the shell cannot write kuhy's checkouts either
    argv = [*wall, tool, "-p", f"{PREAMBLE} {scope}\n\n{task}", "--permission-mode"]
    argv += ["bypassPermissions", "--disallowedTools", *DENY, *src_deny(src), "--settings", HOOKS_OFF]
    # Lean context: no ~/.claude user config, no skills, only the tools a session uses.
    argv += ["--setting-sources", SETTING_SOURCES, "--disable-slash-commands", "--tools", TOOLS]
    log.parent.mkdir(parents=True, exist_ok=True)
    card, stray = worktree.parent, functools.partial(_issue, run_dir, child, "checkout")  # T2515
    if unguarded:
        stray(f"{src} stays writable ({unguarded}): edits there are only logged")
    attempt = 0
    while True:
        attempt += 1
        began = time.time()
        srcguard.begin(card, log.stem, child or None, everywhere=not wall)
        code = _attempt(argv, worktree, log)
        srcguard.end(card, log.stem, child or None, time.time(), stray)
        killed = _killed(code)
        if run_dir is not None:
            workers.record(run_dir, {
                "child": child, "attempt": attempt, "start": began, "end": time.time(), "exit": code,
                "killed": killed, "log": str(log),
            })  # fmt: skip
        if not killed:
            break
        _issue(run_dir, child, "killed", f"worker killed by a signal (exit {code}), attempt {attempt}")
        if attempt == MAX_ATTEMPTS:
            return KILLED
        time.sleep(PAUSE * attempt)
    text = log.read_text(encoding="utf-8", errors="replace")
    changed = _state(worktree) != before
    if not changed and GRILL in text:
        _issue(run_dir, child, "start", GRILLING)
    elif not changed:
        _issue(run_dir, child, "output", f"no edit, exit {code}: {answer(text)}", _model(text))
    return 0 if changed else NO_WORK


def answer(text: str) -> str:
    """Return the tail of the worker's own words: the startup warnings would fill the 500 chars alone."""
    lines = [ln for ln in text.splitlines() if not ln.startswith(NOISE)]
    return "\n".join(lines).strip()[-TAIL:]


def _model(text: str) -> str | None:
    """Return the model the log names (Claude Code prints it in its unrecognized-model line), if any."""
    found = MODEL.search(text)
    return found.group(1) if found else None


def _issue(run_dir: Path | None, child: str, phase: str, symptom: str, model: str | None = None) -> None:
    if run_dir is not None:
        issues.append(
            run_dir, time.time(), child, phase, symptom, "the manager takes this child over", model=model
        )


def main(argv: list[str] | None = None) -> int:
    """Parse `<worktree> <prompt file> <log> [--issues FILE] [--child REPO]` and run the worker.

    `wait <log>... [--timeout S]` instead waits for workers (`workerwait`). A worker marks itself beside its
    log (`<log>.pid` while it runs, `<log>.exit` when over) so that wait needs no model.
    """
    args_in = sys.argv[1:] if argv is None else argv
    if args_in[:1] == ["wait"]:
        return workerwait.main(args_in[1:])
    parser = argparse.ArgumentParser(prog="freeworker")
    parser.add_argument("worktree", type=Path)
    parser.add_argument("prompt_file", type=Path)
    parser.add_argument("log", type=Path)
    parser.add_argument("--issues", type=Path, help="run dir holding free-issues.jsonl")
    parser.add_argument("--child", default="")
    args = parser.parse_args(args_in)
    workerwait.mark_started(args.log)
    code = 1  # a crash of this wrapper itself
    try:
        code = run(args.worktree, args.prompt_file, args.log, run_dir=args.issues, child=args.child)
    finally:
        workerwait.mark_exit(args.log, code)
    print(f"worker exit={code}", flush=True)
    return code


if __name__ == "__main__":
    sys.exit(main())
