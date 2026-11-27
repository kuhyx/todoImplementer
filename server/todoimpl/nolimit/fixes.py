"""What a fresh board worktree needs before its gate (deps), and the tokenless fixes the runner applies.

Setup installs the locked deps the gate needs, from the local stores when it can (`pnpm --prefer-offline`,
`uv sync --frozen`). Autofixes are the repo's own formatters and fixers, picked from its config: ruff
(`[tool.ruff]` or `ruff.toml`), and eslint and prettier on exactly the paths the repo's own `package.json`
scripts run them on (T2550: `eslint .` crashed on a repo that lints `src` only). A fixer that finds errors it
cannot fix exits 0 here (the gate reports them); only a crash makes an autofix red.
"""

from __future__ import annotations

import json
import re
import shlex
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

PNPM_SETUP = "pnpm install --frozen-lockfile --prefer-offline --reporter=silent"
UV_SETUP = "uv sync --frozen --quiet"
PUB_SETUP = "flutter pub get --enforce-lockfile"
SETUP = (
    ("pnpm-lock.yaml", "setup-pnpm", PNPM_SETUP),
    ("uv.lock", "setup-uv", UV_SETUP),
    ("pubspec.lock", "setup-pub", PUB_SETUP),
)
RUFF_FIX = "{run}ruff check --fix-only --exit-zero --quiet . && {run}ruff format --quiet ."
ESLINT_FIX = (
    "pnpm exec eslint --fix --quiet {args} ; test $? -le 1"  # 1 = errors left for the gate, 2 = a crash
)
PRETTIER_FIX = "pnpm exec prettier --write --log-level warn {args}"
# `<tool> <args>` up to the next `&&`, `||`, `;` or `|` of a package.json script
CALL = r"(?:^|[;&|]\s*)(?:(?:pnpm exec|pnpm|npx)\s+)?{tool}\s+([^;&|]+)"
CHECK_FLAGS = re.compile(r"(?:^|\s)(?:--check|-c|--list-different|-l)(?=\s|$)")


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return ""


def locked(wt: Path, lockfile: str) -> list[str]:
    """Return the dirs, relative to `wt`, that hold `lockfile`: the root first, then its direct subdirs."""
    root = ["."] if (wt / lockfile).is_file() else []
    return root + sorted(p.parent.name for p in wt.glob(f"*/{lockfile}") if not p.parent.name.startswith("."))


def in_dir(rel: str, command: str) -> str:
    """Return `command` run in `rel` (the worktree root needs no `cd`)."""
    return command if rel == "." else f"cd {shlex.quote(rel)} && {command}"


def setup(wt: Path) -> list[tuple[str, str]]:
    """Return the dep installs the worktree's lockfiles ask for, as (step name, command).

    Every lockfile at the root or one dir down counts (an app's `app/pubspec.lock`, a `web/pnpm-lock.yaml`):
    installing them fills the shared stores (pnpm store, uv cache, pub cache), so the next turn's installs
    run offline (DOCS-nolimit.md #9).
    """
    found = []
    for lockfile, name, command in SETUP:
        found += [
            (name if rel == "." else f"{name}-{rel}", in_dir(rel, command)) for rel in locked(wt, lockfile)
        ]
    return found


def autofix(wt: Path) -> list[tuple[str, str]]:
    """Return the repo's own fixers, as (step name, command)."""
    found = []
    if "[tool.ruff" in _text(wt / "pyproject.toml") or (wt / "ruff.toml").is_file():
        run = "uv run --frozen " if (wt / "uv.lock").is_file() else ""
        found.append(("fix-ruff", RUFF_FIX.format(run=run)))
    if (wt / "pnpm-lock.yaml").is_file():
        scripts = _scripts(wt)
        if (args := _args(scripts, "eslint")) is not None:
            found.append(("fix-eslint", ESLINT_FIX.format(args=args)))
        if (args := _args(scripts, "prettier")) is not None:
            found.append(("fix-prettier", PRETTIER_FIX.format(args=CHECK_FLAGS.sub("", args).strip())))
    return found


def _scripts(wt: Path) -> list[str]:
    """Return the command strings of `package.json` `scripts`; none when it is missing or malformed."""
    try:
        data = json.loads(_text(wt / "package.json"))
    except ValueError:
        return []
    scripts = data.get("scripts") if isinstance(data, dict) else None
    return [v for v in scripts.values() if isinstance(v, str)] if isinstance(scripts, dict) else []


def _args(scripts: list[str], tool: str) -> str | None:
    """Return the arguments of the first script call of `tool`, None when no script runs it."""
    pattern = re.compile(CALL.format(tool=tool))
    hits = (pattern.search(script) for script in scripts)
    return next((hit.group(1).strip() for hit in hits if hit is not None), None)
