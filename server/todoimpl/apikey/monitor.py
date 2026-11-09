"""Watches the key at server start and hourly: one todo task per problem; the board banner shows it too.

Runs whether or not the key is used and whatever the credit balance is. The board reads `latest()`, so a
request never waits on the network.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from datetime import date
from typing import TYPE_CHECKING

from todoimpl.service.cards import card_tasks
from todoimpl.todo_mcp.model import TodoError

from . import cache, store
from .keystatus import ROTATE_COMMAND, KeyStatus, status

if TYPE_CHECKING:
    from todoimpl.todo_mcp.client import TodoClient

log = logging.getLogger("todoimpl.apikey")
REPO = "kuhyx/todoImplementer"
TITLE = "MANUAL WORK REQUIRED: rotate Claude API key"
COMMAND = ROTATE_COMMAND
INTERVAL = 3600.0
POLL = 30.0


def _default_check(today: date) -> KeyStatus:
    return status(today=today)


class KeyMonitor:
    """`tick()` checks once; `start()` runs it now, every `interval` s and whenever a key file changes."""

    def __init__(  # noqa: PLR0913 - the collaborators; all injectable for tests
        self,
        client: TodoClient,
        *,
        check: Callable[[date], KeyStatus] = _default_check,
        clock: Callable[[], date] = date.today,
        interval: float = INTERVAL,
        poll: float = POLL,
        after_write: Callable[[], None] = lambda: None,
    ) -> None:
        """Nothing runs until tick() or start()."""
        self._client = client
        self._check, self._clock = check, clock
        self._interval, self._poll, self._after_write = interval, poll, after_write
        self._latest: KeyStatus | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def latest(self) -> KeyStatus | None:
        """Return the newest status, None before the first check finished."""
        return self._latest

    def tick(self) -> None:
        """Check and sync the todo task. Never raises."""
        try:
            current = self._check(self._clock())
        except Exception:
            log.exception("api key check crashed")
            return
        self._latest = current
        cache.put(current)
        self._sync_task(current)

    def _sync_task(self, current: KeyStatus) -> None:
        """Create the manual-work task once while the status is not ok; close it once it is ok again."""
        try:
            open_items = [
                card.item
                for note in self._client.list_tasks(repo=REPO, full=True)
                for card in card_tasks(note)
                if card.title == TITLE and card.status != "done"
            ]
            if current.state == "ok":
                for item in open_items:
                    self._client.close_item(item, f"API key status ok again: {current.detail}")
                changed = bool(open_items)
            else:
                changed = not open_items
                if changed:
                    when = current.expires or "unknown"
                    body = f"State: {current.state}. Expires: {when}. {current.detail}.\n\nRun: {COMMAND}"
                    self._client.add_task(REPO, TITLE, body, priority="high")
            if changed:
                self._after_write()
        except TodoError as error:
            log.warning("todo task for the api key not synced: %s", error)

    def _stamp(self) -> tuple[int, int]:
        """Modification times of the key and its metadata (0 when absent): a change means rotate ran."""
        stamps = []
        for path in (store.key_path(), store.meta_path()):
            try:
                stamps.append(path.stat().st_mtime_ns)
            except OSError:
                stamps.append(0)
        return stamps[0], stamps[1]

    def start(self) -> None:
        """Run the loop in a daemon thread (idempotent); the first tick happens off the startup path."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="apikey-monitor", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the loop and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        last, stamp = time.monotonic(), self._stamp()
        self.tick()
        while not self._stop.wait(self._poll):
            now, seen = time.monotonic(), self._stamp()
            if now - last >= self._interval or seen != stamp:
                last, stamp = now, seen
                self.tick()
