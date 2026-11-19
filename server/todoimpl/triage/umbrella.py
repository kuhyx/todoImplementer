"""An `all_repos` note becomes an umbrella note in place (DOCS-umbrella.md): one child per touched repo.

The repos are filtered by a fact, not by the model: `git grep -F <token>` in each local clone (inside `path`
when given), so "repos whose CI has a package-version check" means the repos whose `.github` has the literal.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.board.repos import is_clone_of, repo_path

if TYPE_CHECKING:
    from collections.abc import Callable

TIMEOUT_S = 20.0
GREP_MATCH = 0


def has_token(clone: Path, token: str, path: str | None) -> bool:
    """Say whether `git grep -F token` finds it in the clone (in `path` when given); errors read as no."""
    argv = ["git", "grep", "-q", "-F", "-e", token, "--", path or "."]
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            argv, cwd=clone, capture_output=True, timeout=TIMEOUT_S, check=False
        )  # fmt: skip
    except subprocess.TimeoutExpired, OSError:
        return False
    return proc.returncode == GREP_MATCH


def matching(
    repos: list[str],
    token: str | None,
    path: str | None,
    find: Callable[[str], Path] = repo_path,
    grep: Callable[[Path, str, str | None], bool] = has_token,
) -> list[str]:
    """Return the repos with a local clone that the change touches (every cloned repo without a token)."""
    out = []
    for repo in repos:
        clone = find(repo)
        if is_clone_of(clone, repo) and (token is None or grep(clone, token, path)):
            out.append(repo)
    return out


def body(title: str, text: str, repos: list[str], note: str) -> str:
    """Return the umbrella body: the marker, a checkbox and a `## ` child per repo, each holding the ask."""
    ask = f"{title}\n\n{text}".strip()
    lines = ["Umbrella: per-repo", *(f"- [ ] {repo} ({note})" for repo in repos)]
    for repo in repos:
        lines += [f"## {repo} ({note})", ask]
    return "\n".join(lines)
