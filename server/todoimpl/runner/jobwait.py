"""Hold a card's drive while its `run_job` unit runs, so the session resumes with the result (jobs.py)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from todoimpl.board.status import WAITS_FOR

from . import jobs, orphans
from .jobs import active, wrap

if TYPE_CHECKING:
    from collections.abc import Callable

    from .pipeline import Driver

__all__ = ["active", "hold", "wrap"]  # the driver's three calls (pipeline.py)
POLL = 2.0  # seconds between looks at the job's exit record (and, without one, its unit)
SHOWN = 80


def hold(d: Driver, sleep: Callable[[float], None] = time.sleep) -> None:
    """Return once the card's job has ended (at once without one); raise CancelledError when kuhy cancels.

    A turn still on record is adopted first: it may be the one that started the job and is yet to be stopped.
    """
    from .pipeline import CancelledError  # noqa: PLC0415 - pipeline imports this module

    run = d.ctx.run_dir
    job = jobs.active(run) if orphans.read(run) is None else None
    if job is None or jobs.exit_code(run, job) is not None:
        return
    st = d.state
    d.activity(f"job {job['id']} ({str(job['command'])[:SHOWN]}) runs; the session resumes when it ends")
    st.extra[WAITS_FOR] = {"who": f"job {job.get('name') or job['id']}", "since": job["started"]}
    d.save()
    d.ctx.publish({"type": "stage", "stage": st.stage})
    try:
        while jobs.exit_code(run, job) is None:
            if d.ctx.cancelled():
                raise CancelledError
            sleep(POLL)
    finally:
        st.extra.pop(WAITS_FOR, None)
        d.save()
        d.ctx.publish({"type": "stage", "stage": st.stage})
