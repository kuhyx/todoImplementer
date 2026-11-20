"""The automatic merge loop: the board applies every valid suggestion itself, no click (T2406, DOCS-merge.md).

One thread, started with the server. Each tick asks the service to classify when notes are new or edited
(it never blocks), then merges every stored group through the same path the CLI uses. A group with a member
that has a live run is left alone and asked again next tick. A failed merge is logged and retried after a
delay that doubles up to an hour, so a broken todo MCP never makes a tight loop.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.http.backend import BackendError

from .live import live_reason

if TYPE_CHECKING:
    from collections.abc import Callable

    from .service import MergeService, Suggestion

log = logging.getLogger("todoimpl.merge.auto")
INTERVAL = 30.0
FIRST_DELAY = 60.0
MAX_DELAY = 3600.0
LIVE = "disabled"  # BackendError code of a merge refused for a live run


class AutoMerge:
    """One thread; `tick()` is the testable step."""

    def __init__(
        self, service: MergeService, *, clock: Callable[[], float] = time.time, interval: float = INTERVAL
    ) -> None:
        """Nothing runs until tick() or start()."""
        self.service, self.clock, self.interval = service, clock, interval
        self._retry: dict[str, tuple[float, float]] = {}  # group id -> (not before, last delay)
        self._stop = threading.Event()

    def start(self) -> None:
        """Start the merge thread."""
        threading.Thread(target=self._loop, name="merge-auto", daemon=True).start()

    def stop(self) -> None:
        """Stop after the current tick."""
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("auto merge tick failed")
            self._stop.wait(self.interval)

    def tick(self) -> list[str]:
        """Classify if due, merge every group that can merge now; return the new note ids."""
        self.service.refresh_if_due()
        merged: list[str] = []
        tried: set[str] = set()
        while (group := self._next(tried)) is not None:
            tried.add(group.id)
            if (new_id := self._merge(group)) is not None:
                merged.append(new_id)
        stored = {group.id for group in self.service.pending()}
        self._retry = {key: row for key, row in self._retry.items() if key in stored}
        return merged

    def _next(self, tried: set[str]) -> Suggestion | None:
        """Return the first group not tried this tick, not waiting out a backoff and with no live run.

        The list is read again after each merge: a cut renumbers the ids of the sections behind it.
        """
        now = self.clock()
        for group in self.service.pending():
            if group.id in tried or self._retry.get(group.id, (0.0, 0.0))[0] > now:
                continue
            if live_reason(self.service.root, [card.id for card in group.members]) is None:
                return group
        return None

    def _merge(self, group: Suggestion) -> str | None:
        try:
            result = self.service.merge(group.id)
        except BackendError as exc:
            if exc.code != LIVE:  # a live run is not a failure: it is asked again next tick
                self._fail(group, exc.message)
            return None
        except Exception as exc:
            log.exception("auto merge of %s failed", group.title)
            self._fail(group, str(exc))
            return None
        self._retry.pop(group.id, None)
        log.info("merged %d notes into %s: %s", len(group.members), result["new_id"], group.title)
        return str(result["new_id"])

    def _fail(self, group: Suggestion, why: str) -> None:
        delay = min(self._retry.get(group.id, (0.0, FIRST_DELAY / 2))[1] * 2, MAX_DELAY)
        self._retry[group.id] = (self.clock() + delay, delay)
        log.warning("merge of %s failed (%s); retry in %d s", group.title, why, delay)
