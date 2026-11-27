"""The board's own worktree of a repo: `<run root>/nolimit/<repo>` on branch `nolimit/<date>`.

kuhy's checkout is touched only by `git fetch` and `git worktree add` (both write inside `.git` alone); every
other command runs in the board worktree. Each tick starts it again from `origin/<default>`, so a commit the
last tick discarded, or a stale branch of another day, never leaks into this one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from todoimpl.board.state import run_root
from todoimpl.runner.worktree import git

if TYPE_CHECKING:
    from pathlib import Path

    from .repos import Repo

DIR = "nolimit"
GIT_LIMIT = 60.0


@dataclass(frozen=True)
class Tree:
    """A prepared board worktree: where it is, its branch and the remote branch it started from."""

    path: Path
    branch: str
    base: str  # e.g. `main`: the branch on origin it tracks and pushes to


def home() -> Path:
    """Return `<run root>/nolimit`, where every board worktree of the runner lives."""
    return run_root() / DIR


def branch_of(now: float) -> str:
    """Return today's branch, `nolimit/<YYYY-MM-DD>` (local date)."""
    return f"nolimit/{time.strftime('%Y-%m-%d', time.localtime(now))}"


def default_branch(checkout: Path) -> str:
    """Return origin's default branch (`origin/HEAD`), else `main`."""
    ref = git(checkout, "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD", check=False)
    found = ref.stdout.strip().removeprefix("origin/")
    return found if ref.returncode == 0 and found else "main"


def prepare(repo: Repo, now: float) -> Tree:
    """Fetch origin in kuhy's checkout, then (re)make the board worktree at `origin/<default>`.

    Raise `runner.worktree.GitError` when git fails or runs past the limit.
    """
    git(repo.path, "fetch", "-q", "origin", timeout=GIT_LIMIT)
    base, branch, path = default_branch(repo.path), branch_of(now), home() / repo.name
    start = f"origin/{base}"
    if (path / ".git").is_file():
        git(path, "checkout", "-q", "-f", "-B", branch, start, timeout=GIT_LIMIT)
        git(path, "clean", "-fdq", timeout=GIT_LIMIT)  # untracked leftovers; ignored deps stay (node_modules)
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        git(repo.path, "worktree", "prune", timeout=GIT_LIMIT)  # a removed dir would block the add
        git(repo.path, "worktree", "add", "-q", "-f", "-B", branch, str(path), start, timeout=GIT_LIMIT)
    _drop_old(path, branch)
    return Tree(path, branch, base)


def _drop_old(path: Path, branch: str) -> None:
    """Delete the runner's branches of other days: what they held was pushed or discarded."""
    refs = git(path, "for-each-ref", "--format=%(refname:short)", "refs/heads/nolimit/", timeout=GIT_LIMIT)
    old = [ref for ref in refs.stdout.split() if ref != branch]
    if old:
        git(path, "branch", "-q", "-D", *old, timeout=GIT_LIMIT)


def changes(tree: Tree) -> str:
    """Return `git status --porcelain`: the changes a commit would take (tracked or new files)."""
    return git(tree.path, "status", "--porcelain", timeout=GIT_LIMIT).stdout.strip()


def dirty(tree: Tree) -> bool:
    """Say whether the worktree has changes to commit."""
    return bool(changes(tree))


def ahead(tree: Tree) -> bool:
    """Say whether the branch holds a commit `origin/<base>` does not."""
    out = git(tree.path, "rev-list", "--count", f"origin/{tree.base}..HEAD", timeout=GIT_LIMIT).stdout
    return out.strip() not in {"", "0"}


def discard(tree: Tree) -> None:
    """Drop every commit and change the tick made: back to `origin/<base>`."""
    git(tree.path, "reset", "-q", "--hard", f"origin/{tree.base}", timeout=GIT_LIMIT)
    git(tree.path, "clean", "-fdq", timeout=GIT_LIMIT)


def discard_changes(tree: Tree) -> None:
    """Drop uncommitted changes and new files; the branch's commits stay."""
    git(tree.path, "reset", "-q", "--hard", "HEAD", timeout=GIT_LIMIT)
    git(tree.path, "clean", "-fdq", timeout=GIT_LIMIT)


def drop_last(tree: Tree) -> None:
    """Drop the branch's newest commit and every change after it."""
    git(tree.path, "reset", "-q", "--hard", "HEAD~1", timeout=GIT_LIMIT)
    git(tree.path, "clean", "-fdq", timeout=GIT_LIMIT)
