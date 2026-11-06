"""Build and spawn one headless `claude -p` turn: argv, env, cwd, and its own process group."""

from __future__ import annotations

import contextlib
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from . import policy

ROLE_MODELS = {
    "spec": "sonnet",
    "plan": "sonnet",
    "implement": "opus",
    "verify": "opus",
    "classify": "haiku",
}
# Sessions load kuhy's real ~/.claude allow rules, which permit pushing; only the Ship click may push.
DENY_ALWAYS = ("Bash(git push:*)", "Bash(git push *)")
DENY_READONLY = ("Edit", "Write", "NotebookEdit")
READONLY_ROLES = frozenset({"classify"})
BG_WAIT_VAR = "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"  # 0: headless claude waits for background subagents


@dataclass(frozen=True)
class Invocation:
    """argv, environment and cwd of one turn."""

    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    notes: tuple[str, ...] = ()


def claude_bin() -> str:
    """`$TODOIMPL_CLAUDE`, else `claude` on PATH, else ~/.local/bin/claude (a systemd PATH may lack it)."""
    found = os.environ.get("TODOIMPL_CLAUDE") or shutil.which("claude")
    return found or str(Path.home() / ".local" / "bin" / "claude")


def model_for(role: str) -> str:  # noqa: D103
    return os.environ.get("TODOIMPL_MODEL") or ROLE_MODELS[role]


def build(  # noqa: PLR0913, PLR0917 - one argv, built in one place
    role: str,
    prompt: str,
    worktree: Path,
    resume: str | None = None,
    extra_dirs: tuple[Path, ...] = (),
    allow: tuple[str, ...] = (),
) -> Invocation:
    """Load kuhy's full setup (no strict MCP); the prompt goes right after -p, before the variadic flags.

    `allow` = the learned allow rules; kuhy's session policy (runner/policy.py) can loosen the rest.
    """
    pol = policy.load()
    argv = [
        claude_bin(),
        "-p",
        prompt,
        "--model",
        model_for(role),
        "--output-format",
        "stream-json",
        "--verbose",
    ]
    argv += [
        "--permission-mode",
        pol.permission_mode,
        "--add-dir",
        str(worktree),
        *map(str, extra_dirs),
        *pol.add_dirs,
    ]
    if resume:
        argv += ["--resume", resume]
    if allow:
        argv += ["--allowedTools", *allow]
    deny = (DENY_ALWAYS if pol.deny is None else pol.deny) + (DENY_READONLY if role in READONLY_ROLES else ())
    if deny:
        argv += ["--disallowedTools", *deny]
    if pol.disable_hooks:
        argv += ["--settings", policy.HOOKS_OFF]
    notes = (pol.warning,) if pol.warning else ()
    return Invocation(tuple(argv), {**os.environ, "CLAUDE_AUTO_CONTINUE": "0", BG_WAIT_VAR: "0"}, worktree, notes)


def spawn(inv: Invocation, stderr: IO[str]) -> subprocess.Popen[str]:
    """Start the turn as a new session (process group) so cancel can kill the whole tree."""
    return subprocess.Popen(  # noqa: S603 - argv list, no shell
        list(inv.argv),
        cwd=inv.cwd,
        env=inv.env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
        errors="replace",
        start_new_session=True,
    )


def _signal_group(pgid: int, sig: signal.Signals) -> None:
    with contextlib.suppress(ProcessLookupError):
        os.killpg(pgid, sig)


def kill_tree(proc: subprocess.Popen[Any], grace: float = 3.0) -> None:
    """SIGTERM the process group, give it `grace` seconds, then SIGKILL whatever is left."""
    _signal_group(proc.pid, signal.SIGTERM)
    with contextlib.suppress(subprocess.TimeoutExpired):
        proc.wait(timeout=grace)
    _signal_group(proc.pid, signal.SIGKILL)
    proc.wait()
