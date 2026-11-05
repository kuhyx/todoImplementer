"""Diff of a task worktree against its base commit, including files git does not track yet."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

PATCH_CAP = 200_000
TIMEOUT = 20


def _git(worktree: Path, args: list[str], index: str) -> str:
    """Run git in the worktree against a private index; return stdout (empty on any git failure)."""
    env = {**os.environ, "GIT_INDEX_FILE": index}
    try:
        done = subprocess.run(  # noqa: S603 - fixed argv, no shell
            ["git", "-C", str(worktree), *args],  # noqa: S607
            capture_output=True,
            text=True,
            check=False,
            timeout=TIMEOUT,
            env=env,
        )
    except OSError, subprocess.TimeoutExpired:
        return ""
    return done.stdout if done.returncode == 0 else ""


def worktree_diff(worktree: str | None, base: str | None) -> dict[str, Any] | None:
    """Return {files, patch, truncated} of the worktree vs `base` (HEAD if unknown); None without a worktree.

    A throwaway index is used so the worktree's own index is never touched; `add -A` there picks up new files.
    """
    if not worktree or not Path(worktree).is_dir():
        return None
    ref = base or "HEAD"
    with tempfile.TemporaryDirectory() as tmp:
        index = str(Path(tmp) / "index")
        _git(Path(worktree), ["read-tree", ref], index)
        _git(Path(worktree), ["add", "-A"], index)
        stat = _git(Path(worktree), ["diff", "--cached", "--numstat", ref], index)
        patch = _git(Path(worktree), ["diff", "--cached", ref], index)
    files = []
    for line in stat.splitlines():
        added, removed, path = line.split("\t", 2)
        files.append(
            {
                "path": path,
                "added": int(added) if added.isdigit() else 0,
                "removed": int(removed) if removed.isdigit() else 0,
            }
        )
    return {"files": files, "patch": patch[:PATCH_CAP], "truncated": len(patch) > PATCH_CAP}
