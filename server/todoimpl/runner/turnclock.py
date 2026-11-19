"""A turn's wall clock that stands still while the turn's only live work waits on the build lock (T2270).

The 4 h limit (`$TODOIMPL_TURN_TIMEOUT`) is for a turn that works too long, not for one queued behind other
cards' builds: one build runs at a time, so a turn's place in that queue is no sign of a stuck turn. Once per
`LOOK_EVERY` the host asks `LockWait`: did the stream stay silent since the last look (claude thinks or writes
nothing) and does a waiter on `build.lock` belong to this card (`bgwait.scan`, a few /proc reads)? Then the
deadline moves on by the time since that look. Any other work, or a stream that grew, lets the clock run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from . import bgwait

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

LOOK_EVERY = 1.0  # seconds between two looks


def _size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:  # claude has written nothing yet
        return 0


class LockWait:
    """Say whether, since the last call, the turn only waited on the build lock (`lock` None: never)."""

    def __init__(self, pid: int | None, run_dir: Path, lock: Path | None, stream: Path) -> None:  # noqa: D107
        self.pid, self.run_dir, self.lock, self.stream = pid, run_dir, lock, stream
        self.size = _size(stream)

    def __call__(self) -> bool:  # noqa: D102 - the class says it
        size, before = _size(self.stream), self.size
        self.size = size
        if self.lock is None or size != before:
            return False
        found = bgwait.scan(self.pid, self.run_dir, self.lock)
        return found is not None and bool(found["lock"])


class Deadline:
    """`limit` s from `now` (None: no limit), moved on by each stretch `waiting` calls a lock wait."""

    def __init__(self, limit: float | None, now: float, waiting: Callable[[], bool]) -> None:  # noqa: D107
        self.at = None if limit is None else now + limit
        self.waiting = waiting
        self.looked = now
        self.paused = 0.0

    def passed(self, now: float) -> bool:
        """Say whether the deadline is over at `now` (monotonic seconds)."""
        if self.at is None:
            return False
        if now - self.looked >= LOOK_EVERY:
            if self.waiting():
                self.at += now - self.looked
                self.paused += now - self.looked
            self.looked = now
        return now >= self.at
