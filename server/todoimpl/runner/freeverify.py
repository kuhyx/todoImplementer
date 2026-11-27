"""Free-model work ships only after Claude re-checked it (T2531): the checks stage asks here first.

A run whose turns went `free` carries `free_unverified`. While Claude is still out it rests on the plan
limit ("waits for Claude verify") and resumes at the checks stage; once Claude can run, it goes back to a
fresh live-check session (never the free one), whose clean end clears the mark (`freeroute.after_turn`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.credits import route

from .freeroute import UNVERIFIED
from .pipeline import LimitHitError

if TYPE_CHECKING:
    from .pipeline import Driver

WAIT = "waits for Claude verify"


def gate(d: Driver) -> str | None:
    """Return "live_check" when Claude must verify now, None when nothing is owed; raise while it is out."""
    st, now = d.state, d.ctx.now()
    if not st.extra.get(UNVERIFIED):
        return None
    if (choice := route.choose(d.ctx.root, now)).route is None:
        d.activity(f"{WAIT}: free-model work ships only after a Claude live check")
        raise LimitHitError(choice.until or now)
    st.extra["fresh"] = True  # the verify turn is a new Claude session, never the free one resumed
    d.activity("Claude verifies the free-model work: a fresh live check")
    return "live_check"
