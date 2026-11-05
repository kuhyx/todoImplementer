"""Per-task git worktrees in the task's repo: `kuhyx/<name>` lives at `~/src/<name>`."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from todoimpl.board.repos import repo_path

from .files import NeedsYouError, worktree_path

OWNER = "kuhyx"
GIT_TIMEOUT = 50.0


class GitError(NeedsYouError):
    """A git command failed; the text carries its stderr tail."""


@dataclass(frozen=True)
class Worktree:
    """A task's worktree; `base_ref` is origin's default branch, `base_sha` the merge base with it."""

    path: Path
    branch: str
    base_sha: str
    base_ref: str
    remote_branch: str


def git(
    cwd: Path, *args: str, check: bool = True, timeout: float | None = None
) -> subprocess.CompletedProcess[str]:
    """Run git with prompts off; a failure (when checked) or a timeout raises GitError."""
    timeout = GIT_TIMEOUT if timeout is None else timeout
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            ["git", *args],  # noqa: S607 - git from PATH (tests put a push-refusing shim first)
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired as exc:
        msg = f"git {' '.join(args)} timed out after {timeout:g} s in {cwd}"
        raise GitError(msg, "run_failed") from exc
    if check and proc.returncode:
        tail = (proc.stderr or proc.stdout).strip()[-600:]
        msg = f"git {' '.join(args)} failed in {cwd}: {tail}"
        raise GitError(msg, "run_failed")
    return proc


def repo_dir(repo: str | None) -> Path:
    """Return the local clone of a note's repo, or NeedsYouError saying what is missing."""
    if not repo:
        msg = "The note has no repo: set kuhyx/<name> on it, or do it yourself"
        raise NeedsYouError(msg, "handed_to_you")
    owner, _, name = repo.rpartition("/")
    if owner not in ("", OWNER):
        msg = f"Repo {repo} is not a {OWNER}/ repo; only ~/src clones of those run here"
        raise NeedsYouError(msg, "run_failed")
    path = repo_path(name)
    if not (path / ".git").exists():
        msg = f"Repo {repo} is not cloned at {path}: clone it there, then start again"
        raise NeedsYouError(msg, "handed_to_you")
    return path


def base_ref(repo: Path) -> tuple[str, str]:  # noqa: D103
    for branch in ("main", "master"):
        if (
            git(
                repo, "rev-parse", "--verify", "--quiet", f"refs/remotes/origin/{branch}", check=False
            ).returncode
            == 0
        ):
            return f"origin/{branch}", branch
    msg = f"{repo} has no origin/main or origin/master to branch from"
    raise NeedsYouError(msg, "run_failed")


def add(repo: Path, root: Path, run_id: str) -> Worktree:
    """Create (or reuse) the run's worktree on branch `todo/<item id>` from origin's default branch."""
    git(repo, "fetch", "--quiet", "origin", check=False)
    ref, remote_branch = base_ref(repo)
    path = worktree_path(root, run_id)
    branch = f"todo/{run_id}"
    if not (path / ".git").exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        git(repo, "worktree", "prune")
        exists = (
            git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0
        )
        git(repo, "worktree", "add", *([str(path), branch] if exists else ["-b", branch, str(path), ref]))
    base = git(path, "merge-base", "HEAD", ref).stdout.strip()
    return Worktree(path, branch, base, ref, remote_branch)


def remove(repo: Path, wt: Path, branch: str) -> None:  # noqa: D103
    git(repo, "worktree", "remove", "--force", str(wt), check=False)
    git(repo, "branch", "-D", branch, check=False)
