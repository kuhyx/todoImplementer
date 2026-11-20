"""kuhy's GitHub repos for the board's repo list and the new-task picker, refreshed off the request path.

The board used to list only the repos of cards that exist (T2413), so a repo with no note yet (a new one)
was in neither the filter nor the picker. This keeps `gh repo list` (triage.repos.gh_repos) one refresh
behind: `get()` never waits for gh, a stale list starts one background refresh, a failed one keeps the old
list and retries after `RETRY_S`.
"""

from __future__ import annotations

import threading
import time
from typing import TYPE_CHECKING

from todoimpl.triage.repos import gh_repos

if TYPE_CHECKING:
    from collections.abc import Callable

TTL_S = 300.0  # a new repo shows on the board within this
RETRY_S = 60.0  # after a failed refresh (gh offline, no internet)


def _thread(job: Callable[[], None]) -> None:
    threading.Thread(target=job, name="known-repos", daemon=True).start()


class KnownRepos:
    """The `owner/name` of every live GitHub repo, as of the last good refresh (empty before the first)."""

    def __init__(
        self,
        fetch: Callable[[], list[str]] | None = None,
        spawn: Callable[[Callable[[], None]], None] = _thread,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        """Nothing is fetched until `get()`."""
        self._fetch, self._spawn, self._clock = (
            fetch or gh_repos,
            spawn,
            clock,
        )  # gh_repos read now: tests patch it
        self._lock = threading.Lock()
        self._next = float("-inf")  # when the next refresh may start
        self._busy = False
        self._repos: list[str] = []

    def get(self) -> list[str]:
        """Return the repos known now; a stale list starts a background refresh and is returned as it is."""
        with self._lock:
            start = not self._busy and self._clock() >= self._next
            self._busy = self._busy or start
        if start:
            self._spawn(self._refresh)
        with self._lock:
            return list(self._repos)

    def _refresh(self) -> None:
        """Fetch once; a failure keeps the old list."""
        try:
            repos, delay = self._fetch(), TTL_S
        except OSError, ValueError, KeyError:
            repos, delay = None, RETRY_S
        with self._lock:
            if repos is not None:
                self._repos = repos
            self._next, self._busy = self._clock() + delay, False
