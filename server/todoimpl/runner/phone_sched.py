"""Engine side of the phone-last flow: list runs waiting on the Pixel, requeue one when it shows in adb."""

from __future__ import annotations

import logging
import shutil
import threading
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.errors.marks import PHONE

from .engine import Engine
from .phone import READY, SERIAL, TRIED, adb_command, attached_serials
from .pipeline import WORK_STAGES

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

log = logging.getLogger("todoimpl.runner")
WATCH_SECS = 20.0
EMULATOR_REPORT = "live_check.emulator.md"


class PhoneWatcher(threading.Thread):
    """Every `interval` seconds: if a run waits on the phone and the Pixel is attached, requeue one."""

    def __init__(  # noqa: D107
        self,
        engine: PhoneEngine,
        *,
        adb: str | None = None,
        serial: str = SERIAL,
        interval: float = WATCH_SECS,
    ) -> None:
        super().__init__(name="phone-watch", daemon=True)
        self.engine, self.adb, self.serial, self.interval = engine, adb, serial, interval
        self._halt = threading.Event()

    def tick(self) -> bool:
        """One poll; adb runs only while some run waits, and every waiting run is requeued.

        A fix that is pushed but not on the phone (`phone_updates`) deploys again when the Pixel is attached.
        """
        cards, tried, updates = (
            self.engine.phone_waiting(),
            self.engine.phone_tried(),
            self.engine.phone_updates(),
        )
        if not cards and not tried and not updates:
            return False
        if self.serial not in attached_serials(self.adb or adb_command()):
            self.engine.phone_unplugged(tried)
            return False
        requeued = [self.engine.phone_attached(card) for card in cards]
        requeued += [self.engine.phone_update_start(card) for card in updates]
        return any(requeued)

    def run(self) -> None:  # noqa: D102
        while not self._halt.wait(self.interval):
            try:
                self.tick()
            except Exception:
                log.exception("phone watch tick failed")

    def stop(self) -> None:  # noqa: D102
        self._halt.set()


class PhoneEngine(Engine):
    """Engine plus the phone queue; `Scheduler` builds on this."""

    watcher: PhoneWatcher | None = None

    def start_phone_watch(self, adb: str | None = None, interval: float = WATCH_SECS) -> PhoneWatcher:
        """Start (once) the watcher thread."""
        if self.watcher is None:
            self.watcher = PhoneWatcher(self, adb=adb, interval=interval)
            self.watcher.start()
        return self.watcher

    def close(self) -> None:  # noqa: D102
        if self.watcher is not None:
            self.watcher.stop()
            self.watcher.join(timeout=2)
        super().close()

    def _resting(self, card: str) -> RunState | None:
        """Return the run's state if it rests on a phone wait with no drive; callers hold the lock."""
        st = self._peek(self.root / card)
        resting = card not in self._active and card not in self._queue
        waits = st is not None and st.extra.get("waiting_phone") and st.last_tag == "A"
        return st if st is not None and resting and waits and st.stage in WORK_STAGES else None

    def _waiting(self, card: str, *, tried: bool = False) -> RunState | None:
        """`_resting`, split by whether a phone-attached turn already asked again (it waits on a replug)."""
        st = self._resting(card)
        wait = st.extra["waiting_phone"] if st is not None else None
        return st if isinstance(wait, dict) and bool(wait.get(TRIED)) == tried else None

    def _cards(self, *, tried: bool) -> list[str]:
        with self._cv:
            ids = (path.parent.name for path in sorted(self.root.glob("*/state.json")))
            return [card for card in ids if self._waiting(card, tried=tried) is not None]

    def _peek(self, run_dir: Path) -> RunState | None:
        try:
            return store.load(run_dir)
        except StateError:
            return None

    def phone_waiting(self) -> list[str]:
        """Cards resting on the phone that the next attach requeues, by id."""
        return self._cards(tried=False)

    def phone_tried(self) -> list[str]:
        """Cards whose phone-attached turn asked again: they rerun only after an unplug and replug."""
        return self._cards(tried=True)

    def updating(self, card: str) -> RunState | None:
        """Return the run of a card whose pushed fix waits for the phone (failed deploy, idle), else None."""
        st = self._peek(self.root / card)
        idle = card not in self._active and card not in self._queue
        return st if st is not None and idle and st.stage == "failed" and PHONE in st.extra else None

    def phone_updates(self) -> list[str]:
        """Cards waiting for the phone to be updated with a fix that is already pushed, by id."""
        with self._cv:
            ids = (path.parent.name for path in sorted(self.root.glob("*/state.json")))
            return [card for card in ids if self.updating(card) is not None]

    def phone_update_start(self, card: str) -> bool:  # noqa: ARG002 - the Scheduler overrides it
        """Restart the Ship of such a card (the Scheduler does); the bare engine cannot start runs."""
        return False

    def phone_unplugged(self, cards: list[str]) -> None:
        """Re-arm the given tried cards once the Pixel is gone, so the next plug-in runs them once."""
        with self._cv:
            for card in cards:
                if (st := self._waiting(card, tried=True)) is not None:
                    st.extra["waiting_phone"].pop(TRIED)
                    self.save(card, st)

    def phone_attached(self, card: str) -> bool:
        """Requeue a waiting run into a phone-attached live check; False when it no longer waits."""
        with self._cv:
            st = self._waiting(card)
            if st is None:
                return False
            run_dir = self.root / card
            if (run_dir / READY).exists():
                (run_dir / READY).replace(run_dir / "phone_ready.used.json")
            if (run_dir / "live_check.md").exists():
                shutil.copyfile(run_dir / "live_check.md", run_dir / EMULATOR_REPORT)
            st.stage, st.last_tag, st.error = "live_check", None, None
            st.extra["phone_attached"] = True
            for key in ("live_fixes", "nudges"):
                st.extra.pop(key, None)
            self.save(card, st)
            self.enqueue(card, first=True)
            return True
