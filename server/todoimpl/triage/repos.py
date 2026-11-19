"""kuhy's repos on GitHub (`gh repo list`), the list triage matches notes against; cached 10 minutes."""

from __future__ import annotations

import contextlib
import json
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable

OWNER = "kuhyx"
TTL = 600.0
TIMEOUT_S = 40.0


def run_gh(argv: list[str]) -> str:
    """Run `gh <argv>` and return stdout; any failure raises OSError (callers fail closed)."""
    try:
        proc = subprocess.run(  # noqa: S603 - argv list, no shell
            ["gh", *argv],  # noqa: S607 - gh from PATH (tests put a shim first)
            capture_output=True, text=True, timeout=TIMEOUT_S, check=False,
        )  # fmt: skip
    except subprocess.TimeoutExpired as exc:
        msg = f"gh {argv[0]} timed out after {TIMEOUT_S:g}s"
        raise OSError(msg) from exc
    if proc.returncode != 0:
        msg = f"gh {argv[0]} failed: {(proc.stderr or proc.stdout).strip()[-200:]}"
        raise OSError(msg)
    return proc.stdout


def gh_repos(gh: Callable[[list[str]], str] = run_gh) -> list[str]:
    """Return `kuhyx/<name>` of every repo the account has (limit 1000: gh lists 30 by default), sorted."""
    rows = json.loads(gh(["repo", "list", OWNER, "--limit", "1000", "--json", "name,isArchived"]))
    return sorted(f"{OWNER}/{row['name']}" for row in rows if not row.get("isArchived"))


class Listing:
    """The repo list with a time-to-live; a failed refresh keeps the old list (empty before the first)."""

    def __init__(
        self, fetch: Callable[[], list[str]] = gh_repos, clock: Callable[[], float] = time.monotonic
    ) -> None:
        """Nothing is fetched until `get()`."""
        self._fetch, self._clock = fetch, clock
        self._at = -TTL
        self._repos: list[str] = []

    def get(self) -> list[str]:
        """Return the repos, refreshed when older than the TTL."""
        if self._clock() - self._at >= TTL:
            self._at = self._clock()  # a failure waits for the next TTL too: no gh call per tick
            with contextlib.suppress(OSError, ValueError, KeyError):
                self._repos = self._fetch()
        return list(self._repos)
