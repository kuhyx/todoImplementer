"""Where a (re)start of a run begins: spec or plan for a fresh one, the stage a failed one stopped in."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.umbrella.sched import start_stage

if TYPE_CHECKING:
    from todoimpl.board.state import RunState
    from todoimpl.todo_mcp.items import Item

SPEC_MARKER = re.compile(r"^\s*(done|verify|done_check)\s*:", re.IGNORECASE | re.MULTILINE)
RESUMABLE = ("spec", "plan", "implement", "live_check", "checks")


def needs_spec(item: Item) -> bool:
    """Spec runs only when the note says neither a done_check nor done/verify lines."""
    return item.done_check is None and not SPEC_MARKER.search(item.body)


def restart_stage(st: RunState, item: Item) -> str:
    """Return the stage a (re)start enters: closing again, the failed stage, the gate after a failed ship."""
    if st.closing:
        return "closing"
    failed = st.extra.get("failed_stage") if st.stage == "failed" else None
    fresh = start_stage(item.body, st, "plan" if st.extra.get("spec_ok") or not needs_spec(item) else "spec")
    resumed = "gate" if failed in ("shipping", "gate") else failed  # a failed Ship goes back to the gate
    return str(resumed) if resumed in (*RESUMABLE, "gate") else fresh
