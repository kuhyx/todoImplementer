"""Live events per task. Activity lines get a seq and land in `<run_dir>/events.jsonl` for SSE replay."""

from __future__ import annotations

import json
import queue
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

EVENTS_FILE = "events.jsonl"
TAIL = 64 * 1024  # bytes read from the end for the newest seq: far more than one activity line
_CLOSE: dict[str, Any] = {"type": "_close"}


def last_seq(directory: Path) -> int:
    """Return the newest activity seq in a run dir's events.jsonl (read from its tail), 0 when it has none."""
    try:
        with (directory / EVENTS_FILE).open("rb") as source:
            source.seek(max(0, source.seek(0, 2) - TAIL))
            tail = source.read().decode("utf-8", "replace")
    except OSError:
        return 0
    for line in reversed(tail.splitlines()):
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and isinstance(found := event.get("seq"), int):
            return found
    return 0


class Bus:
    """Fan-out of live events; `subscribe` blocks between events until `close`."""

    def __init__(self, root: Path) -> None:  # noqa: D107
        self._root = root
        self._lock = threading.Lock()
        self._seq: dict[str, int] = {}
        self._subs: dict[str, list[queue.SimpleQueue[dict[str, Any]]]] = {}

    def history(self, id8: str, after: int) -> list[dict[str, Any]]:
        """Return persisted activity events with a seq above `after`; torn lines are skipped."""
        path = self._root / id8 / EVENTS_FILE
        out = []
        for line in path.read_text(encoding="utf-8").splitlines() if path.exists() else []:
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("seq", 0) > after:
                out.append(event)
        return out

    def _next_seq(self, id8: str) -> int:
        if id8 not in self._seq:
            self._seq[id8] = max((e["seq"] for e in self.history(id8, 0)), default=0)
        self._seq[id8] += 1
        return self._seq[id8]

    def publish(self, id8: str, event: dict[str, Any]) -> None:  # noqa: D102
        with self._lock:
            if event.get("type") == "activity":
                event = {**event, "seq": self._next_seq(id8)}
                path = self._root / id8 / EVENTS_FILE
                path.parent.mkdir(parents=True, exist_ok=True)
                with path.open("a", encoding="utf-8") as out:
                    out.write(json.dumps(event, ensure_ascii=False) + "\n")
            for sub in self._subs.get(id8, []):
                sub.put(event)

    def subscribe(self, id8: str, after: int = 0) -> Iterator[dict[str, Any]]:
        """Replay activity newer than `after`, then live events; registering and replay share one lock."""
        sub: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        with self._lock:
            self._subs.setdefault(id8, []).append(sub)
            replay = self.history(id8, after)
        try:
            yield from replay
            while (event := sub.get()) is not _CLOSE:
                yield event
        finally:
            with self._lock:
                self._subs[id8].remove(sub)

    def subscribers(self, id8: str) -> int:  # noqa: D102
        with self._lock:
            return len(self._subs.get(id8, []))

    def close(self) -> None:
        """End every subscription (server shutdown)."""
        with self._lock:
            for subs in self._subs.values():
                for sub in subs:
                    sub.put(_CLOSE)
