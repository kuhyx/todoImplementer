"""The stall watch: every 10 s, each running card quiet for over 60 s is one logged, filed episode (T2402).

kuhy's rule (2026-11-20): no running card sits more than one minute between two real activities; every
time one does, it is logged and becomes a fix-it ticket with the highest priority. An episode is one quiet
stretch of one card (keyed by its `since`): it is filed once, however many ticks it lasts, and its end is
logged with how long it was quiet.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import TYPE_CHECKING

from todoimpl.runner import heavybuild

from . import cause, hold, report, scan, slowstep

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

log = logging.getLogger("todoimpl.stall")
LIMIT = 60.0  # seconds a running card may go without real activity
INTERVAL = 10.0


class StallWatch:
    """One thread; `tick()` is the testable step."""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], float] = time.time,
        diagnose: Callable[[scan.Running], tuple[str, str]] = cause.diagnose,
        interval: float = INTERVAL,
    ) -> None:
        """Nothing runs until tick() or start()."""
        self.root, self.clock, self.diagnose, self.interval = root, clock, diagnose, interval
        self._stop = threading.Event()

    def start(self) -> None:
        """Start the watch thread."""
        threading.Thread(target=self._loop, name="stall-watch", daemon=True).start()

    def stop(self) -> None:
        """Stop after the current tick."""
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.tick()
            except Exception:
                log.exception("stall tick failed")
            self._stop.wait(self.interval)

    def tick(self) -> None:
        """File each new episode, log each ended one, remember the open ones."""
        now = self.clock()
        filed = report.open_episodes(self.root)
        runs = scan.running(self.root)
        before = hold.load(self.root)
        held = hold.review(self.root, before, {r.card: r.since for r in runs}, now, LIMIT)
        still: dict[str, float] = {}
        for run in runs:
            if now - run.since <= LIMIT:
                continue
            if filed.get(run.card) == run.since:
                still[run.card] = run.since
                continue
            if hold.holds(held, run, now):  # a sub-agent's request is out: judged by its answer (T2563)
                continue
            still[run.card] = run.since
            self._file(run, now)
        for card, since in filed.items():
            if still.get(card) != since:
                report.log(self.root, {"at": now, "card": card, "since": since, "ended": now})
        if still != filed:
            report.save_open(self.root, still)
        if held != before:
            hold.save(self.root, held)

    def _file(self, run: scan.Running, now: float) -> None:
        """File one new episode: against the card's repo for its own gate or test step, else the board."""
        signature, detail = self.diagnose(run)
        idle = round(now - run.since)
        # If it's a stall-job on a repo's own gate/test step, file against that repo instead
        job = detail.removeprefix("waits on: ")
        step = slowstep.step_of(job)
        if signature.startswith("stall-job-") and step is not None:
            repo = heavybuild.repo_of(self.root, run.card)
            if repo is not None and repo != report.REPO:
                slowstep.file(repo, step, f"card {run.card} quiet {idle} s: {detail}", now)
                row = {
                    "at": now,
                    "card": run.card,
                    "since": run.since,
                    "idle": idle,
                    "signature": signature,
                    "repo": repo,
                }
                report.log(self.root, {**row, "detail": detail})
                log.warning("card %s quiet %d s -> repo %s: %s", run.card, idle, repo, detail)
                return
        report.file(signature, f"card {run.card} quiet {idle} s: {detail}", now)
        row = {"at": now, "card": run.card, "since": run.since, "idle": idle, "signature": signature}
        report.log(self.root, {**row, "detail": detail})
        log.warning("card %s quiet %d s: %s", run.card, idle, detail)
