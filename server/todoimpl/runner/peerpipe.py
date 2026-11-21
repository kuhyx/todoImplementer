"""The turn host's side of peer delivery: claude reads its prompt and every peer message from one FIFO.

`claude -p --input-format stream-json` takes user messages on stdin while it works and reads each new one at
its next tool-call boundary, inside the same turn (probed on 2.1.330); `--replay-user-messages` echoes each
into the stream, which is how the server knows it was read. The host makes `<run>/peer.fifo.new`, hands
its read end to claude, writes the prompt as the first message, then renames it to `peer.fifo`: from then
on the server may write. At the turn's first `result` the FIFO is unlinked and the host's write end closed,
so claude sees EOF and exits as a plain `-p` turn does. Nothing here outlives the host.
"""

from __future__ import annotations

import contextlib
import json
import os
import threading
from typing import TYPE_CHECKING

from todoimpl.peer.pipe import FIFO

if TYPE_CHECKING:
    from pathlib import Path

NEW = f"{FIFO}.new"
FLAGS = ("--input-format", "stream-json", "--replay-user-messages")
RESULT = b'"type":"result"'  # claude's key order varies: a hit is parsed to be sure
JOIN = 1.0  # seconds close() waits for the prompt writer


def stdin_argv(argv: list[str]) -> tuple[list[str], str] | None:
    """(argv without the prompt, plus the stdin flags; the prompt), or None when there is no `-p <prompt>`."""
    if "-p" not in argv:
        return None
    at = argv.index("-p")
    if at + 1 >= len(argv):
        return None
    return [*argv[: at + 1], *argv[at + 2 :], *FLAGS], argv[at + 1]


def _is_result(line: bytes) -> bool:
    try:
        found = json.loads(line)
    except ValueError:
        return False
    return isinstance(found, dict) and found.get("type") == "result"


class HostPipe:
    """One turn's FIFO: `stdin` goes to Popen, then `started`, `watch` per tick, `close` at the end."""

    def __init__(self, run_dir: Path, prompt: str, rd: int, wr: int) -> None:  # noqa: D107
        self._run, self._prompt, self.stdin, self._wr = run_dir, prompt, rd, wr
        self._lock = threading.Lock()
        self._closed = False
        self._offset = 0
        self.ready = threading.Event()
        self._writer = threading.Thread(target=self._feed, daemon=True)

    @classmethod
    def create(cls, run_dir: Path, prompt: str) -> HostPipe:
        """Make the FIFO (any stale one goes first) and open both ends."""
        for name in (FIFO, NEW):
            (run_dir / name).unlink(missing_ok=True)
        os.mkfifo(run_dir / NEW, 0o600)
        rd = os.open(run_dir / NEW, os.O_RDONLY | os.O_NONBLOCK)
        wr = os.open(run_dir / NEW, os.O_WRONLY)
        os.set_blocking(rd, True)
        return cls(run_dir, prompt, rd, wr)

    def started(self) -> None:
        """Claude holds the read end now: drop the host's copy and feed the prompt."""
        os.close(self.stdin)
        self._writer.start()

    def _feed(self) -> None:
        line = json.dumps({"type": "user", "message": {"role": "user", "content": self._prompt}}) + "\n"
        data = memoryview(line.encode())
        try:
            while data:
                data = data[os.write(self._wr, data) :]
        except OSError:  # claude died before reading it all
            return
        with self._lock:
            if not self._closed:
                (self._run / NEW).replace(self._run / FIFO)
                self.ready.set()

    def watch(self, stream: Path) -> None:
        """Close once the stream holds the turn's result."""
        try:
            with stream.open("rb") as handle:
                handle.seek(self._offset)
                chunk = handle.read()
        except OSError:
            return
        whole = chunk[: chunk.rfind(b"\n") + 1]
        self._offset += len(whole)
        if any(RESULT in line and _is_result(line) for line in whole.splitlines()):
            self.close()

    def close(self) -> None:
        """No more messages: unlink the FIFO and close the write end (claude reads EOF)."""
        with self._lock:
            if self._closed:
                return
            self._closed = True
            for name in (FIFO, NEW):
                (self._run / name).unlink(missing_ok=True)
        self._writer.join(JOIN)
        with contextlib.suppress(OSError):
            os.close(self._wr)
