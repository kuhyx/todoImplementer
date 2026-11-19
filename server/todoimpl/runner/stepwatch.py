"""Where a board check or ship step waits, shown on its card and written to events.jsonl (T2185).

`run_check` knows the queue time (before the lock or the light slot is its) and the run time apart, but
it has no card. The Driver of a run installs a `Watch` in a context variable for its whole drive; `run_check`
finds it there. While a check queues, the card's line reads `⏳🔒 <holder> <HH:MM>` (the `waits_for` object
an idle turn's wait uses; `bgwait.holder` names the holder); when the check ends one event line records
both times. Umbrella round checks run in pool threads: they take a copy of the context.
"""

from __future__ import annotations

import contextlib
import contextvars
import functools
import threading
from typing import TYPE_CHECKING, Any

from todoimpl.board.status import WAITS_FOR

from .files import read_json, write_json

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

    from .pipeline import Driver


class Watch:
    """What the checks of one drive queue on; the card shows the longest-waiting one."""

    def __init__(self, say: Callable[[str], None], show: Callable[[dict[str, Any] | None], None]) -> None:
        """`say` writes an activity line, `show` puts a wait on the card's line (None takes it off)."""
        self.say, self._show = say, show
        self._mutex = threading.Lock()
        self._waits: dict[int, dict[str, Any]] = {}

    def queued(self, key: int, wait: dict[str, Any]) -> None:
        """Show a queued check (the oldest, when several wait)."""
        with self._mutex:
            if self._waits.get(key) != wait:  # a poll that sees the same wait again changes nothing
                self._waits[key] = wait
                self._show(self._oldest())

    def started(self, key: int) -> None:
        """Take a check off the card once it has its lock (or never queued); show the next wait."""
        with self._mutex:
            if self._waits.pop(key, None) is not None:
                self._show(self._oldest())

    def _oldest(self) -> dict[str, Any] | None:
        waits = list(self._waits.values())
        return min(waits, key=lambda w: w.get("since") or 0.0) if waits else None


_WATCH: contextvars.ContextVar[Watch | None] = contextvars.ContextVar("todoimpl_stepwatch", default=None)


def current() -> Watch | None:
    """Return the watch of the drive this code runs in, None outside a drive."""
    return _WATCH.get()


@contextlib.contextmanager
def watching(watch: Watch) -> Iterator[None]:
    """Install `watch` for the code inside (one drive)."""
    token = _WATCH.set(watch)
    try:
        yield
    finally:
        _WATCH.reset(token)


WAIT_FILE = "wait.json"  # in a host's record dir: the wait of the check it runs, for the server's poll loop


def host_watch(path: Path) -> Watch:
    """Return the watch of a gate or deploy host: it has no card, so a wait goes to `path` for the server."""

    def show(found: dict[str, Any] | None) -> None:
        if found is None:
            path.unlink(missing_ok=True)
        else:
            write_json(path, found, durable=False)

    return Watch(lambda _text: None, show)


def relay(path: Path) -> None:
    """Show a host's wait file on the card (the poll loop calls this); no file: take the wait off."""
    if (watch := current()) is None:
        return
    found = read_json(path)
    if isinstance(found, dict):
        watch.queued(hash(path), found)
    else:
        watch.started(hash(path))


def _show(driver: Driver, found: dict[str, Any] | None) -> None:
    """Put a check's wait into the card's line (or take it off): save, then announce, as an idle turn does."""
    if found is None:
        driver.state.extra.pop(WAITS_FOR, None)
    else:
        driver.state.extra[WAITS_FOR] = found
    driver.save()
    driver.ctx.publish({"type": "stage", "stage": driver.state.stage})


def drive(run: Callable[[Driver], None]) -> Callable[[Driver], None]:
    """Decorate `Driver.run`: the drive's checks report their queue and run time through a `Watch`."""

    @functools.wraps(run)
    def wrapper(driver: Driver) -> None:
        driver.state.extra.pop(WAITS_FOR, None)  # a wait saved before a restart is no longer known
        watch = Watch(driver.activity, functools.partial(_show, driver))
        with watching(watch):
            run(driver)
        driver.state.extra.pop(WAITS_FOR, None)

    return wrapper
