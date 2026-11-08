"""A server stand-in the detach tests SIGKILL: one Scheduler drives one card from `$TODOIMPL_HOME`.

Run as `python detach_server.py <card>`; the parent test owns the world (HOME, PATH shims, fake claude dir).
"""

from __future__ import annotations

import sys
import time

from runnerfakes import FakeClient, task
from todoimpl.runner.scheduler import Scheduler


def main(card: str) -> None:
    """Start the card and idle until the test kills this process."""
    sched = Scheduler(FakeClient({card.split("-", maxsplit=1)[0]: task(done_check="true")}), check_timeout=20)
    sched.start(card)
    time.sleep(120)


if __name__ == "__main__":
    main(sys.argv[1])
