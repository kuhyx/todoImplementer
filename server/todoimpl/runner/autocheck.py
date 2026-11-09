"""Auto close: poll trusted done_checks of open items and start a `closing` run when one turns green.

The trust rule is todo-hooks' own, re-implemented read-only (that CLI stays untouched): the allow-list is
`$TODO_HOOKS_TRUST_FILE` or `~/.config/todo-hooks/trusted-checks`, first token per line is
`sha256(done_check.strip())`, `#` lines are ignored and a missing file trusts nothing. The switch is
`$TODOIMPL_HOME/settings.json` `auto_close` (absent = off), re-read every tick. Results go to
`$TODOIMPL_HOME/autocheck.json`; it is deleted while the switch is off, so the first tick after turning it on
finds no file and records a baseline: what passes then is never auto-started.
"""

from __future__ import annotations

import hashlib
import logging
import os
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.usage.limits import limit_state

from .checks import run_capped
from .files import NeedsYouError, read_json, write_json
from .worktree import repo_dir

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

log = logging.getLogger("todoimpl.autocheck")
CACHE = "autocheck.json"
SETTINGS = "settings.json"
INTERVAL = 300.0
POLL_TIMEOUT = 60.0
CLOSED = ("done", "abandoned")
RESTARTABLE = ("failed", "cancelled")
UNTRUSTED = "untrusted check (not in trusted-checks)"
NOTE_LEVEL = "note-level check ignored (multi-item note)"
NO_REPO = "no repo checkout"
TIMED_OUT = "check timed out"
WAITING = "waiting for a pass"
BASELINE = "passes, auto skipped (baseline)"
DEFERRED = "passes, auto start deferred (usage limit)"
STARTED = "passed, closing run started"
RUN_EXISTS = "passes, a run already exists"


class CardLike(Protocol):
    """What the poll reads from a board card (service.cards.CardTask)."""

    @property
    def id(self) -> str: ...  # noqa: D102
    @property
    def repo(self) -> str | None: ...  # noqa: D102
    @property
    def status(self) -> str: ...  # noqa: D102
    @property
    def done_check(self) -> str | None: ...  # noqa: D102
    @property
    def note_check(self) -> str | None: ...  # noqa: D102


class Starter(Protocol):
    """The Scheduler's locked "create the run dir if absent" start of a closing run."""

    def auto_start(self, card: str, passed_at: float) -> bool: ...  # noqa: D102


def trust_file() -> Path:  # noqa: D103
    found = os.environ.get("TODO_HOOKS_TRUST_FILE")
    return Path(found) if found else Path.home() / ".config" / "todo-hooks" / "trusted-checks"


def check_hash(done_check: str) -> str:
    """todo-hooks' preimage, byte for byte: sha256 of the stripped check, UTF-8."""
    return hashlib.sha256(done_check.strip().encode()).hexdigest()


def load_trusted(path: Path) -> set[str]:
    """Return the hashes in the trust file; an unreadable or missing file trusts nothing."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return set()
    return {
        row.split()[0].lower()
        for row in text.splitlines()
        if row.strip() and not row.lstrip().startswith("#")
    }


def enabled(root: Path) -> bool:
    """Return the `auto_close` switch of settings.json; absent, unreadable or not `true` means off."""
    data = read_json(root / SETTINGS)
    return isinstance(data, dict) and data.get("auto_close") is True


def load_cache(root: Path) -> dict[str, dict[str, Any]]:
    """Return autocheck.json (`{item id: {at, passed, trusted, reason, pending}}`), {} when absent or bad."""
    data = read_json(root / CACHE)
    return {k: v for k, v in data.items() if isinstance(v, dict)} if isinstance(data, dict) else {}


# One writer at a time: the poll's whole-file rewrite and a red server re-run of a single item.
_CACHE_LOCK = threading.Lock()


def note_red(root: Path, card: str, now: float) -> None:
    """Mark the item's poll entry red after the server's own re-run failed, so Start is disabled at once."""
    path = root / CACHE
    with _CACHE_LOCK:
        if not path.exists():
            return  # the switch is off: there is no poll to correct
        data = load_cache(root)
        data[card] = _entry(now, WAITING, trusted=True)
        write_json(path, data)


def _entry(
    now: float, reason: str, *, trusted: bool, passed: bool = False, pending: bool = False
) -> dict[str, Any]:
    return {"at": now, "passed": passed, "trusted": trusted, "reason": reason, "pending": pending}


class AutoCloser:
    """One poll thread: a tick every `interval` s (the first at once), one check at a time, no overlap."""

    def __init__(  # noqa: PLR0913 - collaborators and knobs, all injectable for tests
        self,
        root: Path,
        cards: Callable[[], Sequence[CardLike]],
        starter: Starter,
        *,
        clock: Callable[[], float] = time.time,
        interval: float = INTERVAL,
        timeout: float = POLL_TIMEOUT,
    ) -> None:
        """Nothing runs until tick() or start()."""
        self.root, self.cards, self.starter = root, cards, starter
        self.clock, self.interval, self.timeout = clock, interval, timeout
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._trusted: set[str] = set()

    def start(self) -> None:
        """Start the poll thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._loop, name="autocheck", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        """Stop the thread after its current check."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(self.timeout + 5)

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("auto-close tick failed")
            self._stop.wait(self.interval)

    def tick(self) -> None:
        """Poll every open item with a done_check once; start a closing run on a red-to-green turn."""
        path = self.root / CACHE
        if not enabled(self.root):
            path.unlink(missing_ok=True)
            return
        baseline = not path.exists()
        prev = load_cache(self.root)
        self._trusted = load_trusted(trust_file())
        fresh: dict[str, dict[str, Any]] = {}
        for card in sorted(self.cards(), key=lambda c: c.id):
            if card.status in CLOSED or not (card.done_check or card.note_check) or self._stop.is_set():
                continue
            entry = self._judge(card, prev.get(card.id), baseline=baseline)
            if entry is not None:
                fresh[card.id] = entry
        with _CACHE_LOCK:
            # An entry written while this tick ran (a red re-run) is newer than the one the tick kept.
            latest = load_cache(self.root)
            for key, entry in fresh.items():
                if latest.get(key, {}).get("at", 0) > entry["at"]:
                    fresh[key] = latest[key]
            write_json(path, fresh)

    def _judge(  # noqa: PLR0911 - one return per reason of the card's auto note
        self, card: CardLike, prev: dict[str, Any] | None, *, baseline: bool
    ) -> dict[str, Any] | None:
        """Return the item's new cache entry; prev is kept as is for an item whose run is not restartable."""
        run = self._run_stage(card.id)
        if run is not None and run not in RESTARTABLE:
            return prev
        check = card.done_check
        if check is None:
            return _entry(self.clock(), NOTE_LEVEL, trusted=check_hash(str(card.note_check)) in self._trusted)
        if check_hash(check) not in self._trusted:
            return _entry(self.clock(), UNTRUSTED, trusted=False)
        try:
            cwd = repo_dir(card.repo)
        except NeedsYouError:
            return _entry(self.clock(), NO_REPO, trusted=True)
        try:
            code = run_capped(check, cwd, self.timeout)
        except OSError:
            code = 127
        now = self.clock()
        if code != 0:
            return _entry(now, TIMED_OUT if code is None else WAITING, trusted=True)
        seen_red = prev is not None and (not prev["passed"] or bool(prev.get("pending")))
        armed = (prev is None and not baseline) or seen_red
        if not armed:
            kept = str(prev["reason"]) if prev is not None and prev.get("passed") else BASELINE
            return _entry(now, kept, trusted=True, passed=True)
        if run is not None:
            return _entry(now, RUN_EXISTS, trusted=True, passed=True)
        if limit_state(self.root).active(now):
            return _entry(now, DEFERRED, trusted=True, passed=True, pending=True)
        started = self.starter.auto_start(card.id, now)
        return _entry(now, STARTED if started else RUN_EXISTS, trusted=True, passed=True)

    def _run_stage(self, card: str) -> str | None:
        """Return the stage of a closing run, a non-restartable marker for any other run, None without one."""
        try:
            st = store.load(self.root / card)
        except StateError:
            return "unreadable"
        if st is None:
            return None
        return st.stage if st.closing else f"{st.stage} (not closing)"
