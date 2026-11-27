"""What a fresh board worktree needs before its gate (deps), and the tokenless fixes the runner applies.

Setup installs the locked deps the gate needs, from the local stores when it can (`pnpm --prefer-offline`,
`uv sync --frozen`). Autofixes are the repo's own formatters and fixers, picked from its config: ruff
(`[tool.ruff]` or `ruff.toml`), eslint and prettier (named in `package.json`, run through pnpm). A fixer that
finds errors it cannot fix exits 0 here (the gate reports them); only a crash makes an autofix red.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

PNPM_SETUP = "pnpm install --frozen-lockfile --prefer-offline --reporter=silent"
UV_SETUP = "uv sync --frozen --quiet"
RUFF_FIX = "{run}ruff check --fix-only --exit-zero --quiet . && {run}ruff format --quiet ."
ESLINT_FIX = "pnpm exec eslint --fix --quiet . ; test $? -le 1"  # 1 = errors left for the gate, 2 = a crash
PRETTIER_FIX = "pnpm exec prettier --write --log-level warn ."


def _text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return ""


def setup(wt: Path) -> list[tuple[str, str]]:
    """Return the dep installs the worktree's lockfiles ask for, as (step name, command)."""
    found = []
    if (wt / "pnpm-lock.yaml").is_file():
        found.append(("setup-pnpm", PNPM_SETUP))
    if (wt / "uv.lock").is_file():
        found.append(("setup-uv", UV_SETUP))
    return found


def autofix(wt: Path) -> list[tuple[str, str]]:
    """Return the repo's own fixers, as (step name, command)."""
    found = []
    if "[tool.ruff" in _text(wt / "pyproject.toml") or (wt / "ruff.toml").is_file():
        run = "uv run --frozen " if (wt / "uv.lock").is_file() else ""
        found.append(("fix-ruff", RUFF_FIX.format(run=run)))
    package = _text(wt / "package.json")
    if (wt / "pnpm-lock.yaml").is_file() and '"eslint"' in package:
        found.append(("fix-eslint", ESLINT_FIX))
    if (wt / "pnpm-lock.yaml").is_file() and '"prettier"' in package:
        found.append(("fix-prettier", PRETTIER_FIX))
    return found
