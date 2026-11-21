"""Build one headless `claude -p` turn (argv, env, cwd); `launch` starts it, `kill_tree` ends a child tree."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from todoimpl.newtask import images

from . import buildlock, mcpconf, policy

ROLE_MODELS = {
    "spec": "sonnet",
    "plan": "sonnet",
    "manager": "opus",  # umbrella rounds: runs the free workers (kuhy, 2026-11-10: opus, not sonnet)
    "closing": "sonnet",
    "implement": "opus",
    "live_check": "sonnet",  # verify-and-report work: its own fresh session, seeded from the handoff
    "verify": "opus",
    "classify": "haiku",
}
# Default reasoning effort per role (the article's yardstick: medium by default); the classifier is plain
# extraction. A fix turn and the cheap tier's retry raise it to high; `--effort` is in claude 2.1.322.
ROLE_EFFORT = {
    "spec": "medium", "plan": "medium", "manager": "medium", "closing": "medium", "implement": "medium",
    "live_check": "medium", "verify": "medium", "classify": "low",
}  # fmt: skip
# Sessions load kuhy's real ~/.claude allow rules, which permit pushing; only the Ship click may push.
DENY_ALWAYS = ("Bash(git push:*)", "Bash(git push *)")
DENY_READONLY = ("Edit", "Write", "NotebookEdit")
READONLY_ROLES = frozenset({"classify", "closing"})
KEY_VAR = "ANTHROPIC_API_KEY"
BG_WAIT_VAR = "CLAUDE_CODE_PRINT_BG_WAIT_CEILING_MS"  # 0: headless claude waits for background subagents


@dataclass(frozen=True)
class Invocation:
    """argv, environment and cwd of one turn; `route` is plan (the `claude` CLI) or credits (Agent SDK)."""

    argv: tuple[str, ...]
    env: dict[str, str]
    cwd: Path
    notes: tuple[str, ...] = ()
    route: str = "plan"


@dataclass(frozen=True)
class Options:
    """What a turn is told, whichever route runs it (the CLI argv and the SDK options both come from this)."""

    prompt: str
    model: str
    permission_mode: str
    add_dirs: tuple[str, ...]
    resume: str | None
    allow: tuple[str, ...]
    deny: tuple[str, ...]
    settings: str
    env: dict[str, str]
    cwd: Path
    notes: tuple[str, ...]
    effort: str = "medium"
    mcp_servers: dict[str, Any] = field(default_factory=dict)  # strict: only these start (mcpconf.py)


def claude_bin() -> str:
    """`$TODOIMPL_CLAUDE`, else `claude` on PATH, else ~/.local/bin/claude (a systemd PATH may lack it)."""
    found = os.environ.get("TODOIMPL_CLAUDE") or shutil.which("claude")
    return found or str(Path.home() / ".local" / "bin" / "claude")


def model_for(role: str) -> str:  # noqa: D103
    return os.environ.get("TODOIMPL_MODEL") or ROLE_MODELS[role]


def effort_for(role: str, effort: str | None = None) -> str:
    """Return the effort of a turn: the one asked for, else the role's default."""
    return effort or ROLE_EFFORT[role]


def options(  # noqa: PLR0913, PLR0917 - one set of turn options, built in one place
    role: str,
    prompt: str,
    worktree: Path,
    resume: str | None = None,
    extra_dirs: tuple[Path, ...] = (),
    allow: tuple[str, ...] = (),
    model: str | None = None,
    effort: str | None = None,
) -> Options:
    """Return what a turn is given; `allow` = learned allow rules, kuhy's session policy loosens the rest."""
    pol = policy.load()
    deny = (DENY_ALWAYS if pol.deny is None else pol.deny) + (DENY_READONLY if role in READONLY_ROLES else ())
    # Each turn is a new process: one owner per card keeps its phone test slot across turns. The plan route
    # never carries the API key (it would take precedence over the plan's login); the credit route adds it.
    # Builds queue on one machine-wide lock (buildlock.py); a turn never starts out holding it.
    env = {k: v for k, v in os.environ.items() if k not in {KEY_VAR, buildlock.HELD_VAR}}
    env |= {
        "CLAUDE_AUTO_CONTINUE": "0",
        BG_WAIT_VAR: "0",
        "PHONE_LEASE_OWNER": f"todoimpl:{worktree.parent.name}",
        **buildlock.turn_env(worktree.parent.name),
    }
    dirs = (
        str(worktree),
        *map(str, (*extra_dirs, *images.session_dirs())),
        *pol.add_dirs,
    )  # images: the note's
    hooks = policy.turn_settings(hooks_off=pol.disable_hooks)
    notes = (pol.warning,) if pol.warning else ()
    return Options(
        prompt,
        model or model_for(role),
        pol.permission_mode,
        dirs,
        resume,
        allow,
        deny,
        hooks,
        env,
        worktree,
        notes,
        effort_for(role, effort),
        mcpconf.servers(worktree),
    )


def build(  # noqa: PLR0913, PLR0917 - one argv, built in one place
    role: str,
    prompt: str,
    worktree: Path,
    resume: str | None = None,
    extra_dirs: tuple[Path, ...] = (),
    allow: tuple[str, ...] = (),
    model: str | None = None,
    effort: str | None = None,
) -> Invocation:
    """Build the plan route: kuhy's full setup but strict MCP (T1986); the prompt goes right after -p."""
    opt = options(role, prompt, worktree, resume, extra_dirs, allow, model, effort)
    argv = [claude_bin(), "-p", prompt, "--model", opt.model, "--output-format", "stream-json", "--verbose"]
    argv += ["--permission-mode", opt.permission_mode, "--add-dir", *opt.add_dirs]
    argv += ["--effort", opt.effort]
    argv += ["--strict-mcp-config", "--mcp-config", json.dumps({"mcpServers": opt.mcp_servers})]
    if resume:
        argv += ["--resume", resume]
    argv += ["--settings", opt.settings]
    if allow:
        argv += ["--allowedTools", *allow]
    if opt.deny:
        argv += ["--disallowedTools", *opt.deny]
    return Invocation(tuple(argv), opt.env, worktree, opt.notes)


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
