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
from typing import IO, TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

QUEUE = "build.queue"
QLOCK = "build.queue.lock"
DIGITS = 12
WIDE = 120  # characters of the command kept in a ticket
RESERVE = 300.0  # s a dead board check's place is kept for its restarted server (T2168)
BOARD = " board"  # a ticket of the server's own checks (`buildlock.held`) ends with this
LINE = re.compile(
    r"(?P<pid>\d+) (?P<state>wait|held|gone) (?P<card>\S+) \((?P<cmd>.*)\) since (?P<at>.+?)"
    r"(?P<board> board)?"
)


@dataclass(frozen=True)
class Ticket:
    """One ticket: number, owner pid, `wait`, `held` or `gone`, card, command, since, board check or not."""

    seq: int
    pid: int
    state: str
    card: str
    command: str
    since: str
    board: bool = False


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
    pid, card, cmd = int(found["pid"]), found["card"], found["cmd"]
    return Ticket(int(path.name), pid, found["state"], card, cmd, found["at"], bool(found["board"]))


def _line(state: str, card: str, command: str) -> str:
    since = time.strftime("%Y-%m-%d %H:%M:%S")
    return f"{os.getpid()} {state} {card} ({command[:WIDE]}) since {since}{BOARD}\n"


def _settle(path: Path, fh: IO[bytes]) -> bool:
    """Deal with a dead ticket we hold the lock of: True when it stays as a board check's reserved place.

    The first look stamps it `gone` (its mtime starts the `RESERVE` window); a later look past the window, or
    any dead session ticket, removes it. A file swapped under us (same name, new inode) is left alone.
    """
    found = _parse(path)
    try:
        same = os.fstat(fh.fileno()).st_ino == path.stat().st_ino
    except FileNotFoundError:
        return False
    if same and found.board and found.state != "gone":
        path.write_text(
            f"{found.pid} gone {found.card} ({found.command}) since {found.since}{BOARD}\n", encoding="utf-8"
        )
        return True
    if same and found.board and time.time() - path.stat().st_mtime < RESERVE:
        return True
    if same:
        path.unlink(missing_ok=True)
    return False


def listing(base: Path) -> list[Ticket]:
    """Return the live tickets in queue order; a dead one found on the way is settled (`_settle`)."""
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
                _settle(path, fh)
    return live


def _wait(mine: Path, on_wait: Callable[[int], None]) -> None:
    """Wait on the nearest earlier ticket until none is left; a reserved place is passed over (T2168)."""
    passed: set[str] = set()
    while earlier := [p for p in tickets(mine.parent.parent) if p.name < mine.name and p.name not in passed]:
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
                passed.clear()  # a passed place may have been taken back meanwhile: look again
            if _settle(earlier[-1], fh):
                passed.add(earlier[-1].name)


def _claim(base: Path, card: str, command: str) -> tuple[Path, IO[str]] | None:
    """Take back this check's own dead place (same card and command, a restarted server), if it is kept."""
    for path in tickets(base):
        found = _parse(path)
        if not (found.board and (found.card, found.command) == (card, command[:WIDE])):
            continue
        try:
            fh = path.open("r+", encoding="utf-8")
        except FileNotFoundError:
            continue
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:  # alive: the same check runs in another thread
            fh.close()
            continue
        if found.state == "gone" and time.time() - path.stat().st_mtime >= RESERVE:
            path.unlink()
            fh.close()
            continue
        fh.truncate(0)
        fh.write(_line("wait", card, command))
        fh.flush()
        return path, fh
    return None


@contextlib.contextmanager
def queued(
    base: Path, card: str, command: str, on_wait: Callable[[int], None]
) -> Iterator[Callable[[], None]]:
    """Take a ticket (or this check's kept place) and wait for its turn; yield a call that marks it held."""
    queue = base / QUEUE
    queue.mkdir(parents=True, exist_ok=True)
    with (base / QLOCK).open("a", encoding="utf-8") as qlock:
        fcntl.flock(qlock, fcntl.LOCK_EX)
        for stale in queue.glob(".new.*"):  # under the queue lock nobody is between create and rename
            stale.unlink(missing_ok=True)
        if (claimed := _claim(base, card, command)) is not None:
            mine, own = claimed
        else:
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
