"""After a usage reset the board files one token optimization note and starts it first (DOCS-credits.md).

Two events count (kuhy, 2026-11-27): the weekly window resetting (`seven_day.resets_at` in the stored probe,
`usage-probe.json`, jumps forward) and the first lift of the plan limit after a card rested `paused_limit`.
Both landing together make ONE note, keyed by the reset instant: a key within `MERGE` of the last one is the
same reset. `reset-watch.json` under the board home holds `last_reset`, `limit_seen`, the last weekly reset
time and the reset still to file or start (`pending`); it is written durably before any note, and the
note's `Reset-Key:` line finds a note a cut tick already filed, so a restart never files a second one.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.board.status import CYCLE_ENDS
from todoimpl.errors.marks import TOKENOPT
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import NewTask
from todoimpl.usage import oauth

from . import limits, tokenopt
from .files import read_json, write_json

if TYPE_CHECKING:
    from todoimpl.errors.ports import Creator, Starter
    from todoimpl.service.cards import CardTask

log = logging.getLogger("todoimpl.runner")
FILE = "reset-watch.json"
INTERVAL = 60.0
JUMP = 86400.0  # a reset moves `resets_at` about a week on; less is the endpoint's jitter
MERGE = 3600.0  # two reset instants this close are one reset (the limit lift and the weekly window)
MISSING_TICKS = 2  # ticks a filed note may be gone (a refresh, a merge) before it counts as closed by hand


def load(root: Path) -> dict[str, Any]:
    """Return the watch's state; a missing or broken file is a first start."""
    data = read_json(root / FILE)
    return {"last_reset": None, "limit_seen": None, **(data if isinstance(data, dict) else {})}


def save(root: Path, data: dict[str, Any]) -> None:
    """Store the state durably (fsync, atomic rename) before anything acts on it."""
    root.mkdir(parents=True, exist_ok=True)
    write_json(root / FILE, data)


def _epoch(key: object) -> float | None:
    try:
        return datetime.fromisoformat(str(key)).timestamp()
    except ValueError:
        return None


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def paused(root: Path) -> bool:
    """Say whether some run rests `paused_limit` (the plan limit holds it)."""
    return any((read_json(p) or {}).get("stage") == "paused_limit" for p in root.glob("*/state.json"))


def weekly(data: dict[str, Any], probe: oauth.Probe | None, now: float) -> str | None:
    """Return the reset key when the weekly window reset since the last probe; record its new end."""
    week = probe.seven_day if probe is not None else None
    if week is None:
        return None
    last = _number(data.get("week_resets_at"))
    data["week_resets_at"] = week.resets_at
    if last is None or week.resets_at - last <= JUMP:
        return None  # a first start only learns the window; a small move is jitter
    return tokenopt.iso(min(last, now))


def lifted(data: dict[str, Any], root: Path, now: float) -> str | None:
    """Return the reset key on the first lift after a card rested `paused_limit`; note a held limit."""
    until = limits.active_until(root, now)
    seen = _number(data.get("limit_seen"))
    if until is not None:
        if paused(root):
            data["limit_seen"] = until
        return None
    data["limit_seen"] = None
    return None if seen is None else tokenopt.iso(min(seen, now))


def accept(data: dict[str, Any], key: str) -> bool:
    """Make `key` the reset to file unless it is the last one again (within `MERGE`)."""
    last, new = _epoch(data.get("last_reset")), _epoch(key)
    if last is not None and new is not None and abs(new - last) < MERGE:
        return False
    data["last_reset"], data["pending"] = key, {"key": key}
    return True


def resting(root: Path, card: str) -> bool:
    """Say whether the card has no run, or one whose cycle is over (a new cycle may start)."""
    try:
        run = store.load(root / card)
    except StateError:
        return False
    return run is None or run.stage in CYCLE_ENDS


def started(root: Path, card: str, key: str) -> bool:
    """Say whether the card's run already carries this reset's mark (a tick cut after the start)."""
    try:
        run = store.load(root / card)
    except StateError:
        return False
    mark = run.extra.get(TOKENOPT) if run is not None else None
    return isinstance(mark, dict) and mark.get("key") == key


@dataclass
class ResetWatch:
    """One thread, a tick every `interval` seconds (the first at once); `tick()` is the testable step.

    Nothing runs until tick() or start(); `feed(card, text)` writes the card's activity line (default: the
    scheduler's bus).
    """

    root: Path
    cards: Callable[[], Sequence[CardTask]]
    creator: Creator
    starter: Starter
    feed: Callable[[str, str], None] | None = None
    clock: Callable[[], float] = time.time
    interval: float = INTERVAL
    _stop: threading.Event = field(default_factory=threading.Event, init=False)
    _thread: threading.Thread | None = field(default=None, init=False)

    def start(self) -> None:
        """Start the thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="reset-watch", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread after its current tick."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(10)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("reset watch tick failed")
            self._stop.wait(self.interval)

    def tick(self) -> None:
        """Notice a reset (one key per tick, the weekly one first), then file and start its note."""
        now, data = self.clock(), load(self.root)
        week = weekly(data, oauth.load(self.root), now)
        lift = lifted(data, self.root, now)
        if (key := week or lift) is not None and accept(data, key):
            log.info("usage reset %s: a token optimization note is due", key)
        save(self.root, data)
        if isinstance(pending := data.get("pending"), dict):
            self._advance(data, pending, now)

    def _advance(self, data: dict[str, Any], pending: dict[str, Any], now: float) -> None:
        key = str(pending.get("key"))
        found = tokenopt.find(self.cards(), key)
        if found is not None:
            pending["card"], pending["missing"] = found.card, 0
        elif "card" in pending:  # filed before: gone from the board for a while means closed by hand
            pending["missing"] = int(pending.get("missing", 0)) + 1
            if pending["missing"] >= MISSING_TICKS:
                data["pending"] = None
            save(self.root, data)
            return
        elif not self._file(pending, key):
            return
        save(self.root, data)
        self._start(data, str(pending["card"]), key, now)

    def _file(self, pending: dict[str, Any], key: str) -> bool:
        """Add the note's part; False when the todo app refused it (the next tick finds or files it)."""
        task = NewTask(tokenopt.REPO, tokenopt.title(key), tokenopt.body(key), (), priority=tokenopt.PRIORITY)
        try:
            _note, card = self.creator.create(task)
        except BackendError as exc:  # the todo app is down, or the part is not on the board yet (its line)
            log.warning("token optimization %s: no note made: %s", key, exc.message)
            return False
        pending["card"], pending["missing"] = card, 0
        return True

    def _start(self, data: dict[str, Any], card: str, key: str, now: float) -> None:
        """Start the card first in the queue, unattended and shipping itself; a busy card waits a tick."""
        if started(self.root, card, key):
            data["pending"] = None
            save(self.root, data)
            return
        if not resting(self.root, card):
            return
        why = tokenopt.ensure_worktree(self.root / card)
        # A refused start (a click won the race) raises: the tick is logged, the next one starts it.
        self.starter.start(card, auto_ship=True, extra={TOKENOPT: {"key": key, "at": now}})
        data["pending"] = None
        save(self.root, data)
        line = f"{tokenopt.FEED} {key[:10]}"
        (self.feed or self._bus_line)(card, line if why is None else f"{line}; no ~/.claude worktree: {why}")

    def _bus_line(self, card: str, text: str) -> None:
        """Publish the activity line on the scheduler's bus (a fake scheduler has none)."""
        bus = getattr(self.starter, "bus", None)
        if bus is not None:
            event = {"type": "activity", "at": self.clock(), "kind": "system", "text": text, "tool": None}
            bus.publish(card, event)
