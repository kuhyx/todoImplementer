"""Hold ceiling (T2166): a build-lock holder whose process tree does nothing for 2 min gives the lock on.

A holder stuck in pipe_read, futex or sleep (a deadlocked script, a poll loop with nothing to poll) kept every
other card queued for 18-21 min. Every `every` s the server samples the holding ticket's tree (the wrapper and
all below it): CPU ticks, bytes read and written, the set of pids and any process in disk sleep. When nothing
moves for `quiet` s it sends SIGUSR1 to the wrapper, which lets go of the lock and its ticket while the tool
runs on (never killed), and the holder's card hears it as an activity event (its `events.jsonl`). A holder
that uses CPU, does I/O or starts processes is never cut. Skipped: the server's own checks (`buildlock.held`,
the server's pid; they have their own timeouts) and a ticket whose pid is no buildlock.sh.
"""

from __future__ import annotations

import logging
import os
import signal
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from . import buildlock, buildqueue

log = logging.getLogger(__name__)
PROC = Path("/proc")
QUIET = 120.0
EVERY = 10.0
TRACE = 0.01  # CPU seconds per second that still count as doing nothing (1 %)
CPU_FIELDS = slice(11, 15)  # utime stime cutime cstime, after the `)` that closes the command name
TICK = os.sysconf("SC_CLK_TCK")


@dataclass
class _Seen:
    seq: int
    cpu: float
    io: int
    pids: frozenset[int]
    at: float
    quiet_since: float


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:  # the process is gone
        return ""


def _tree(root: int) -> list[int]:
    found, todo = [], [root]
    while todo:
        pid = todo.pop()
        found.append(pid)
        for task in (PROC / str(pid) / "task").glob("*"):
            todo.extend(int(kid) for kid in _read(task / "children").split())
    return found


def _sample(root: int) -> tuple[float, int, frozenset[int], bool]:
    """Return the tree's CPU seconds, bytes read and written, pids, and whether any is in disk sleep."""
    cpu, io, disk = 0.0, 0, False
    pids = _tree(root)
    for pid in pids:
        fields = _read(PROC / str(pid) / "stat").rpartition(")")[2].split()
        if len(fields) > CPU_FIELDS.stop:
            cpu += sum(int(f) for f in fields[CPU_FIELDS]) / TICK
            disk = disk or fields[0] == "D"
        for line in _read(PROC / str(pid) / "io").splitlines():
            if line.startswith(("rchar:", "wchar:")):
                io += int(line.split()[1])
    return cpu, io, frozenset(pids), disk


def _card(head: buildqueue.Ticket, base: Path) -> str | None:
    """Return the ticket's card, else the run dir its wrapper works in (a `systemd-run` job has no card)."""
    if head.card != "?":
        return head.card
    try:
        rel = (PROC / str(head.pid) / "cwd").readlink().relative_to(base)
    except OSError, ValueError:
        return None
    return rel.parts[0] if rel.parts else None


class Ceiling:
    """Watch the build-lock holder; `tick()` looks once (tests call it), `start()` runs it every `every` s."""

    def __init__(self, sink: object, *, quiet: float = QUIET, every: float = EVERY) -> None:
        """`sink` is the scheduler: its `bus` (when it has one) tells the holder's card."""
        self._sink, self.quiet, self._every = sink, quiet, every
        self._seen: _Seen | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start the daemon thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="hold-ceiling", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread and wait for it."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(5)

    def _loop(self) -> None:
        while not self._stop.wait(self._every):
            try:
                self.tick()
            except Exception:
                log.exception("hold ceiling tick failed")

    def tick(self) -> None:
        """Sample the holder once; cut it when its tree has been quiet for `quiet` s."""
        base = buildlock.root()
        live = buildqueue.listing(base)
        head = live[0] if live and live[0].state == "held" else None
        if (
            head is None
            or head.pid == os.getpid()
            or buildlock.WRAPPER not in _read(PROC / str(head.pid) / "cmdline")
        ):
            self._seen = None
            return
        cpu, io, pids, disk = _sample(head.pid)
        now, seen = time.monotonic(), self._seen
        moved = seen is None or seen.seq != head.seq or disk or pids != seen.pids or io != seen.io
        if moved or seen is None or cpu - seen.cpu > TRACE * max(now - seen.at, 0.1):
            self._seen = _Seen(head.seq, cpu, io, pids, now, now)
            return
        seen.cpu, seen.at = cpu, now
        if now - seen.quiet_since >= self.quiet:
            self._seen = None
            self._cut(head, base)

    def _cut(self, head: buildqueue.Ticket, base: Path) -> None:
        try:
            os.kill(head.pid, signal.SIGUSR1)
        except ProcessLookupError:
            return
        text = (
            f"build lock taken back from {head.command}: no CPU, disk or new process for {self.quiet:g} s; "
            "the next build in the queue runs, this one runs on without the lock"
        )
        log.warning("%s (ticket %d, pid %d)", text, head.seq, head.pid)
        card, bus = _card(head, base), getattr(self._sink, "bus", None)
        if card is not None and bus is not None:
            bus.publish(
                card, {"type": "activity", "at": time.time(), "kind": "system", "text": text, "tool": None}
            )
