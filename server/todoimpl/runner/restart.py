"""Where a (re)start of a run begins: spec or plan for a fresh one, the stage a failed one stopped in."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.umbrella.sched import start_stage

from . import deployline, hold, retry

if TYPE_CHECKING:
    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

INTERRUPTED = "Ship was interrupted by a restart"  # the error older servers parked a cut Ship with
MAX_RESUMES = 2  # Ship resumes at once per click; past them each resume waits a step of the retry ladder
SPEC_MARKER = re.compile(r"^\s*(done|verify|done_check)\s*:", re.IGNORECASE | re.MULTILINE)
RESUMABLE = ("spec", "plan", "implement", "live_check", "checks")


def needs_spec(item: Item) -> bool:
    """Spec runs only when the note says neither a done_check nor done/verify lines."""
    return item.done_check is None and not SPEC_MARKER.search(item.body)


def resume_ship(st: RunState, now: float) -> None:
    """Count one automatic resume of a Ship a restart cut (T1988); it always goes on, never to kuhy (T2510).

    Ship is idempotent and a restart is the board's own business (a deploy of todoImplementer), so the first
    `MAX_RESUMES` resumes go on at once and each later one rests in `paused_retry` for the next ladder step
    (1, 2, 5, 10, then 30 min): a Ship that itself keeps restarting the board slows down instead of parking.
    """
    done = int(st.extra.get("ship_resumes", 0))
    st.extra["ship_resumes"] = done + 1
    if done >= MAX_RESUMES:
        wait = retry.later(st, now, f"Ship was cut by {done + 1} restarts in a row: it goes on", "killed")
        retry.pause(st, wait.until, wait.why, wait.kind)


def restart_stage(st: RunState, item: Item) -> str:
    """Return the stage a (re)start enters: closing again, the failed stage, the gate after a failed ship."""
    if st.closing:
        return "closing"
    failed = st.extra.get("failed_stage") if st.stage == "failed" else None
    cut = str(st.error).startswith(INTERRUPTED)  # a restart cut the Ship (also the legacy "gate" form)
    if (failed == "shipping" and str(st.error).startswith(deployline.PREFIX)) or (
        failed in ("shipping", "gate") and cut
    ):  # Ship is idempotent (pushed.json, origin): it goes on, no second click
        return "shipping"
    fresh = start_stage(item.body, st, "plan" if st.extra.get("spec_ok") or not needs_spec(item) else "spec")
    if failed in ("shipping", "gate"):  # a failed Ship goes again: back to the gate only where one is held
        return "gate" if hold.held() else "shipping"
    return str(failed) if failed in RESUMABLE else fresh
