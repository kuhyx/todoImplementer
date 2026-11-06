"""Engine side of the phone-last flow: list runs waiting on the Pixel, requeue one when it shows in adb."""

from __future__ import annotations

import logging
import shutil
import threading
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError

from .engine import Engine
from .phone import READY, SERIAL, adb_command, attached_serials
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
        """One poll; adb runs only while some run waits, and one run is requeued per tick."""
        cards = self.engine.phone_waiting()
        if not cards or self.serial not in attached_serials(self.adb or adb_command()):
            return False
        return self.engine.phone_attached(cards[0])

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

    def _waiting(self, card: str) -> RunState | None:
        """Return the run's state if it rests on a phone wait with no drive; callers hold the lock."""
        st = self._peek(self.root / card)
        resting = card not in self._active and card not in self._queue
        waits = st is not None and st.extra.get("waiting_phone") and st.last_tag == "A"
        return st if st is not None and resting and waits and st.stage in WORK_STAGES else None

    def _phone_busy(self) -> bool:
        return any(
            (st := self._peek(path.parent)) is not None
            and st.extra.get("phone_attached")
            and (st.task_id in self._active or st.task_id in self._queue)
            for path in self.root.glob("*/state.json")
        )

    def _peek(self, run_dir: Path) -> RunState | None:
        try:
            return store.load(run_dir)
        except StateError:
            return None

    def phone_waiting(self) -> list[str]:
        """Cards resting on the phone, oldest first; none while another run is using the phone."""
        with self._cv:
            if self._phone_busy():
                return []
            ids = (path.parent.name for path in sorted(self.root.glob("*/state.json")))
            return [card for card in ids if self._waiting(card) is not None]

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
