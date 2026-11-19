"""The build lock's ticket queue, the same protocol as buildlock.sh: builds run in arrival order (T2164).

flock alone is not FIFO: on a loaded PC a woken waiter is slow to run and a later arrival takes the lock in
that gap, so one card waited ~20 min behind newer ones. Now each waiter writes
`<root>/build.queue/<12 digits>` (the next number, under `build.queue.lock`) and holds an flock on that
ticket while it waits and while it builds. It waits on the nearest earlier ticket until none is left, then
takes `build.lock`, which stays the one mutex (old wrappers and hand-held locks still exclude). A ticket whose
flock anyone can take is dead: its owner was killed or the PC rebooted; the next look removes it, so no stale
ticket blocks the queue.
A ticket's line: `<pid> <wait|held> <card> (<cmd>) since <time>`.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

QUEUE = "build.queue"
QLOCK = "build.queue.lock"
DIGITS = 12
LINE = re.compile(r"(?P<pid>\d+) (?P<state>wait|held) (?P<card>\S+) \((?P<cmd>.*)\) since (?P<at>.+)")


@dataclass(frozen=True)
class Ticket:
    """One live ticket: its number, owner pid, `wait` or `held`, card, command and since when."""

    seq: int
    pid: int
    state: str
    card: str
    command: str
    since: str


def tickets(base: Path) -> list[Path]:
    """Return the ticket files under `base`, oldest first (live or not)."""
    queue = base / QUEUE
    found = queue.glob("[0-9]*") if queue.is_dir() else ()
    return sorted(p for p in found if p.name.isdigit())


def _parse(path: Path) -> Ticket:
    try:
        text = path.read_text(encoding="utf-8").strip()
    except OSError:
        text = ""
    found = LINE.fullmatch(text)
    if found is None:
        return Ticket(int(path.name), 0, "wait", "?", "", "")
    return Ticket(int(path.name), int(found["pid"]), found["state"], found["card"], found["cmd"], found["at"])


def listing(base: Path) -> list[Ticket]:
    """Return the live tickets in queue order; a dead one found on the way is removed."""
    live = []
    for path in tickets(base):
        try:
            fh = path.open("rb")
        except FileNotFoundError:
            continue
        with fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                live.append(_parse(path))
            else:
                path.unlink(missing_ok=True)
    return live


def _line(state: str, card: str, command: str) -> str:
    return f"{os.getpid()} {state} {card} ({command[:120]}) since {time.strftime('%Y-%m-%d %H:%M:%S')}\n"


def _wait(mine: Path, on_wait: Callable[[int], None]) -> None:
    """Wait on the nearest earlier ticket until none is left; a ticket whose lock we get is dead."""
    while earlier := [p for p in tickets(mine.parent.parent) if p.name < mine.name]:
        try:
            fh = earlier[-1].open("rb")
        except FileNotFoundError:
            continue
        with fh:
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                on_wait(len(earlier))
                fcntl.flock(fh, fcntl.LOCK_EX)
            earlier[-1].unlink(missing_ok=True)


@contextlib.contextmanager
def queued(
    base: Path, card: str, command: str, on_wait: Callable[[int], None]
) -> Iterator[Callable[[], None]]:
    """Take a ticket and wait for its turn; yield a call that marks it held. `on_wait(ahead)` hears a wait."""
    queue = base / QUEUE
    queue.mkdir(parents=True, exist_ok=True)
    with (base / QLOCK).open("a", encoding="utf-8") as qlock:
        fcntl.flock(qlock, fcntl.LOCK_EX)
        for stale in queue.glob(".new.*"):  # under the queue lock nobody is between create and rename
            stale.unlink(missing_ok=True)
        mine = queue / f"{max((int(p.name) for p in tickets(base)), default=0) + 1:0{DIGITS}d}"
        fresh = queue / f".new.{os.getpid()}"
        own = fresh.open("w", encoding="utf-8")
        fcntl.flock(own, fcntl.LOCK_EX)
        own.write(_line("wait", card, command))
        own.flush()
        fresh.rename(mine)

    def mark() -> None:
        mine.write_text(_line("held", card, command), encoding="utf-8")  # same inode: the lock stays

    try:
        _wait(mine, on_wait)
        yield mark
    finally:
        mine.unlink(missing_ok=True)
        own.close()
