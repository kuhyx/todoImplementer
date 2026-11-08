"""Follow a turn through its files: what a restarted server finds, and the tail that reads a stream.

A turn is over when its host wrote `<stem>.exit.json` (checked before the last read, so the read after it sees
the whole stream). A turn whose host is gone with no exit record is lost: the caller takes the "killed" path.
`<stem>.fed` holds the stream offset already shown in the live feed, so an adopted turn replays its stream
into the parser without publishing the feed a second time.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from . import launch, orphans
from .files import EXIT_SUFFIX, STREAM_SUFFIX, read_json, sibling, write_json

if TYPE_CHECKING:
    import threading
    from collections.abc import Callable
    from pathlib import Path

    from .stream import StreamParser

POLL = 0.05  # a change shows within 100 ms
START_GRACE = 30.0  # a launched host that has not recorded itself by then never started
FED_SUFFIX = ".fed"


class Detached(BaseException):
    """The server is closing: the follower lets go and leaves the turn running."""


def reap_legacy(run_dir: Path) -> bool:
    """Kill a turn the previous server version (pipe-spawned, no stem) left running: nobody can read it.

    Return whether there was such a record (the turn counts as lost, once).
    """
    rec = orphans.read(run_dir)
    if rec is None or rec.stem is not None:
        return False
    orphans.reap(run_dir)
    return True


def abandon(run_dir: Path) -> None:
    """Stop whatever turn the record names and forget it (a cancel with no drive to do it)."""
    rec = orphans.read(run_dir)
    if rec is None:
        return
    if rec.stem is None:
        orphans.reap(run_dir)
    else:
        launch.handle_for(run_dir, rec).stop()
        orphans.clear(run_dir)


def exit_code(run_dir: Path, stem: str) -> int:
    """Return the code in `<stem>.exit.json` (negative: killed by that signal)."""
    return int((read_json(sibling(run_dir, stem, EXIT_SUFFIX)) or {}).get("code", -1))


def host_alive(run_dir: Path, rec: orphans.Record) -> bool:
    """Say whether the host can still write an exit record; a new one gets `START_GRACE` to appear."""
    rec = orphans.read(run_dir) or rec
    if rec.host_pid is None:
        return time.time() - rec.launched < START_GRACE
    return orphans.alive(rec.host_pid, rec.host_start)


def _read_from(path: Path, pos: int) -> bytes:
    try:
        with path.open("rb") as stream:
            stream.seek(pos)
            return stream.read()
    except FileNotFoundError:
        return b""


class _Feed:
    """Parse a turn's lines; publish only those past the `.fed` offset, and move that offset on."""

    def __init__(
        self, parser: StreamParser, activity: Callable[[str, str, str | None], None], fed: Path
    ) -> None:
        self.parser, self.activity, self.path = parser, activity, fed
        self.fed = int(read_json(fed) or 0)
        self.base = 0

    def _emit(self, line: bytes, *, show: bool) -> None:
        for act in self.parser.feed(line.decode("utf-8", "replace")):
            if show:
                self.activity(act.kind, act.text, act.tool)

    def lines(self, lines: list[bytes]) -> None:
        """Take complete lines (each one byte longer on disk: its newline)."""
        for line in lines:
            self.base += len(line) + 1
            self._emit(line, show=self.base > self.fed)
        if lines and self.base > self.fed:
            self.fed = self.base
            write_json(self.path, self.fed)

    def last(self, partial: bytes) -> None:
        """Take the unterminated last line of a finished stream."""
        self._emit(partial, show=True)


def follow(
    run_dir: Path,
    rec: orphans.Record,
    parser: StreamParser,
    activity: Callable[[str, str, str | None], None],
    detach: threading.Event,
) -> int | None:
    """Feed the turn's stream to `parser` until it is over; return claude's exit code, None if it was lost.

    Complete lines only (a partial one waits for the rest); lines below the `.fed` offset are parsed silently.
    """
    stem = str(rec.stem)
    stream, over = sibling(run_dir, stem, STREAM_SUFFIX), sibling(run_dir, stem, EXIT_SUFFIX)
    feed = _Feed(parser, activity, sibling(run_dir, stem, FED_SUFFIX))
    pos = 0
    buf = b""
    while True:
        if detach.is_set():
            raise Detached
        ended = over.exists()
        chunk = _read_from(stream, pos)
        pos += len(chunk)
        *lines, buf = (buf + chunk).split(b"\n")
        feed.lines(lines)
        if chunk:
            continue
        if ended:
            feed.last(buf)
            return exit_code(run_dir, stem)
        if not host_alive(run_dir, rec) and not over.exists():
            return None
        time.sleep(POLL)
