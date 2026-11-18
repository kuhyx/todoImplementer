"""Background-refreshed snapshot of the todo notes, so /api/board never waits on the MCP server."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from todoimpl.repotask.ids import norm
from todoimpl.todo_mcp.model import UnreachableError

if TYPE_CHECKING:
    from collections.abc import Callable

    from .cards import CardTask
    from .runtitles import RunTitles

log = logging.getLogger("todoimpl.service")
INTERVAL = 4.0
NOT_LOADED = "notes not loaded yet"


@dataclass(frozen=True)
class Snapshot:
    """The last good cards plus the error of the latest refresh (None when it succeeded)."""

    tasks: tuple[CardTask, ...] = ()
    error: str | None = NOT_LOADED
    at: float = 0.0
    loaded: bool = False  # True once any fetch succeeded: the cards may be stale, but they were real


def _overlay(tasks: tuple[CardTask, ...], repo: str, cards: tuple[CardTask, ...]) -> tuple[CardTask, ...]:
    """Swap the repo's open cards for `cards` (a fresh read of that repo); every other card stays."""
    ids = {card.id for card in cards}
    kept = [
        t for t in tasks if t.id not in ids and not (t.repo and norm(t.repo) == repo and t.status != "done")
    ]
    return (*kept, *cards)


class TaskCache:
    """Holds a Snapshot; refresh() runs fetch, a daemon thread repeats it `interval` s after each finish."""

    def __init__(
        self,
        fetch: Callable[[], list[CardTask]],
        interval: float = INTERVAL,
        clock: Callable[[], float] = time.time,
        repo_fetch: Callable[[str], list[CardTask]] | None = None,
    ) -> None:
        """Nothing is fetched until refresh() or start(); `repo_fetch` reads one repo (refresh_repo)."""
        self._fetch = fetch
        self._repo_fetch = repo_fetch
        self._seq = 0  # counts repo patches, so a full fetch knows which ones came after it began
        self._patches: dict[str, tuple[int, tuple[CardTask, ...]]] = {}
        self._interval = interval
        self._clock = clock
        self._snap = Snapshot()
        self.run_titles: RunTitles | None = None  # names of run dirs no card shows (set by build_backend)
        self._lock = threading.Lock()
        self._flight = threading.Lock()  # held while a fetch runs (single-flight)
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None

    def snapshot(self) -> Snapshot:
        """Return the current snapshot without touching the network."""
        with self._lock:
            return self._snap

    def refresh(self, *, fresh: bool = False) -> Snapshot:
        """Fetch now; a failure keeps the old cards but records why, it never reads as an empty board.

        Single-flight (T2005): while a fetch runs, a second refresh returns the current snapshot and
        opens no connection. `fresh` waits that fetch out and runs one that starts after the call, so a
        caller that just wrote a note sees it (T2046).
        """
        if not self._flight.acquire(blocking=fresh):
            return self.snapshot()
        try:
            return self._refresh()
        finally:
            self._flight.release()

    def refresh_repo(self, repo: str) -> Snapshot:
        """Read one repo's cards now and lay them over the snapshot: seconds, where a whole board takes ~30 s.

        A full fetch that began before this read keeps the patch on top when it lands (T2046). Without a
        `repo_fetch` it is a full fetch that starts after the call. A todo-app error propagates.
        """
        if self._repo_fetch is None:
            return self.refresh(fresh=True)
        key, cards = norm(repo), tuple(self._repo_fetch(repo))
        with self._lock:
            self._seq += 1
            self._patches[key] = (self._seq, cards)
            self._snap = replace(self._snap, tasks=_overlay(self._snap.tasks, key, cards))
            return self._snap

    def _laid_over(self, tasks: tuple[CardTask, ...], began: int) -> tuple[CardTask, ...]:
        """Drop the patches the fetch saw; lay the newer ones over its cards (call with the lock held)."""
        self._patches = {k: v for k, v in self._patches.items() if v[0] > began}
        for key, (_, cards) in self._patches.items():
            tasks = _overlay(tasks, key, cards)
        return tasks

    def _refresh(self) -> Snapshot:
        with self._lock:
            began = self._seq
        try:
            tasks = tuple(self._fetch())
            with self._lock:
                tasks = self._laid_over(tasks, began)
            fresh = Snapshot(tasks, None, self._clock(), loaded=True)
        except Exception as exc:  # noqa: BLE001 - the loop must survive anything; the message reaches the page
            log.warning("todo refresh failed: %s", exc)
            # An outage reads as itself, not as "TodoError: <whatever the sick server last said>".
            text = str(exc) if isinstance(exc, UnreachableError) else f"{type(exc).__name__}: {exc}"
            with self._lock:
                fresh = replace(self._snap, error=text, at=self._clock())
        with self._lock:
            self._snap = fresh
        return fresh

    def poke(self) -> None:
        """Refresh as soon as possible (after an action changed a note)."""
        self._wake.set()

    def start(self) -> None:
        """Start the refresh thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="todo-cache", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        self._stop.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            self._wake.wait(self._interval)
            self._wake.clear()
            if not self._stop.is_set():
                self.refresh()
