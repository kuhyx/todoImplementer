"""What a work turn's status tag line decides: rest, move on, continue, or nudge for the missing tag."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .files import NeedsYouError

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .stream import TurnResult

MAX_NUDGES = 2
MAX_R_CONTINUES = 3


def r_continue(st: RunState, res: TurnResult) -> str | None:
    """Resume the same stage with a continue prompt after an `R:` turn, up to MAX_R_CONTINUES times."""
    conts = int(st.extra.get("r_continues", 0))
    if res.tag != "R" or conts >= MAX_R_CONTINUES:
        return None
    st.extra["r_continues"] = conts + 1
    st.extra["r_continue"] = True
    return st.stage


def after_tag(st: RunState, res: TurnResult, nxt: str) -> str | None:
    """Q/A rests for kuhy, D moves on, R continues the session, no tag nudges, then one fresh retry."""
    if res.tag in ("Q", "A"):
        return None
    if res.tag == "D":
        for key in ("nudges", "r_continues", "tagless_retry"):
            st.extra.pop(key, None)
        return nxt
    if (again := r_continue(st, res)) is not None:
        return again
    nudges = int(st.extra.get("nudges", 0)) + 1
    if nudges > MAX_NUDGES:
        if st.extra.get("tagless_retry"):
            msg = f"Claude ended {nudges} turns without a status tag: read the feed and send guidance"
            raise NeedsYouError(msg, "run_failed")
        st.extra["tagless_retry"] = True
        st.extra["fresh"] = True
        return st.stage
    st.extra["nudges"] = nudges
    st.extra["nudge"] = True
    return st.stage
