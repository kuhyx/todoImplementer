"""Which GitHub repo a session's cwd pushes to: `git -C <cwd> remote get-url origin` read as `owner/name`.

The GET list asks this for every row that could move, and the page polls every 10 s (the relay every 5 s), so
answers are kept per cwd for a minute: a handful of distinct directories cost a handful of git calls a minute.
"""

from __future__ import annotations

import re
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.board.repos import is_clone_of, repo_path
from todoimpl.tokens_api import paths

if TYPE_CHECKING:
    from todoimpl.sessions.commands import CommandRunner

REPO = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
# https (credentials allowed), ssh:// and scp-style git@ URLs of github.com; `.git` and a slash optional.
_GITHUB = re.compile(
    r"(?:https://(?:[^@/\s]+@)?github\.com/|ssh://git@github\.com/|git@github\.com:)"
    r"(?P<repo>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?"
)
TTL_SECONDS = 60.0
GIT_TIMEOUT = 5.0

# The clock, as a seam so tests can age the cache.
now = time.monotonic


def github_repo(url: str) -> str | None:
    """Return `owner/name` of a github.com remote URL, or None for anything else."""
    found = _GITHUB.fullmatch(url.strip())
    return found.group("repo") if found else None


def has_clone(repo: str) -> bool:
    """Say whether the board has a clone to run `repo` in (`board/repos.py`, the rule the runner uses)."""
    return is_clone_of(repo_path(repo), repo)


class OriginCache:
    """`cwd -> owner/name or None`, each answer kept for TTL_SECONDS."""

    def __init__(self) -> None:
        """Start empty."""
        self._seen: dict[str, tuple[float, str | None]] = {}
        self._lock = threading.Lock()

    def repo(self, runner: CommandRunner, cwd: str) -> str | None:
        """Return the GitHub repo of the clone at `cwd`, asking git at most once a minute per cwd."""
        with self._lock:
            hit = self._seen.get(cwd)
            if hit is not None and now() - hit[0] < TTL_SECONDS:
                return hit[1]
        argv = ("git", "-C", str(paths.sysroot_path(cwd)), "remote", "get-url", "origin")
        result = runner.run(argv, timeout=GIT_TIMEOUT)
        found = github_repo(result.stdout) if result.ok else None
        with self._lock:
            self._seen[cwd] = (now(), found)
        return found


# One per process, like the transcript scanner; tests swap in a fresh one.
CACHE = OriginCache()
