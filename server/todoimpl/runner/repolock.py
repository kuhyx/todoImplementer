"""One run at a time per repo (DOCS-repotask.md, "Per-repo lock").

A repo's task, an umbrella child of that repo and an older per-section run each hold the repo while they
drive. A run whose turn survived a restart joins with `force`: it is already working, so it never waits, but a
run that starts later waits for it. Holders are card or child run ids, so `waits()` can name what a
queued run waits on.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from todoimpl.repotask.ids import norm

if TYPE_CHECKING:
    from collections.abc import Callable

POLL = 0.5


class RepoLocks:
    """Thread-safe map repo -> the runs holding it, plus who waits on whom."""

    def __init__(self) -> None:
        """Start with no holders."""
        self._mutex = threading.Lock()
        self._held: dict[str, set[str]] = {}
        self._waits: dict[str, str] = {}

    def acquire(self, repo: str, holder: str, *, force: bool = False) -> str | None:
        """Take the repo for `holder`; return None, or the holder in the way (and note the wait)."""
        key = norm(repo)
        with self._mutex:
            others = self._held.get(key, set()) - {holder}
            if others and not force:
                self._waits[holder] = min(others)
                return self._waits[holder]
            self._held.setdefault(key, set()).add(holder)
            self._waits.pop(holder, None)
            return None

    def release(self, holder: str) -> None:
        """Let go of every repo `holder` holds and forget that it waited."""
        with self._mutex:
            self._waits.pop(holder, None)
            for key in list(self._held):
                self._held[key].discard(holder)
                if not self._held[key]:
                    del self._held[key]

    def wait(self, repo: str, holder: str, stop: Callable[[], bool], *, force: bool = False) -> bool:
        """Block until `holder` has the repo; False when `stop()` says to give up; `force` never waits."""
        gate = threading.Event()
        while self.acquire(repo, holder, force=force) is not None:
            if stop():
                self.release(holder)
                return False
            gate.wait(POLL)
        return True

    def waits(self) -> dict[str, str]:
        """Return waiter -> the holder it waits on."""
        with self._mutex:
            return dict(self._waits)

    def free(self, repo: str, holder: str) -> bool:
        """Say whether nobody but `holder` holds the repo."""
        with self._mutex:
            return not self._held.get(norm(repo), set()) - {holder}
