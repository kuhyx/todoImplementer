"""Before each implement turn a repo task re-reads its parts: kuhy's new part is worked next (T2581).

The drive fetches the card once, so a part kuhy added while the run worked an automatic one stayed out of the
prompt and the tick command refused its key until the next cycle. Now every implement turn takes the fresh
parts (`files.snapshot`, the order of `service/repocards.py`: kuhy's first). A kuhy part that is new since
the last snapshot also gets a one-shot note: switch to it now, the automatic part waits unticked.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from todoimpl.repotask import files, lane
from todoimpl.todo_mcp.model import TodoError

from .files import read_json

if TYPE_CHECKING:
    from todoimpl.repotask.model import Part

    from .engine import Client
    from .pipeline import Driver

log = logging.getLogger("todoimpl.runner")
IMPLEMENT = "implement"
SWITCH = (
    "(runner) kuhy added {parts} while you worked. His parts come before automatic ones: switch to them "
    "now. Leave the automatic part you were on unticked and finish it after his. End with a `D:`, `Q:` or "
    "`A:` tag line."
)


def _new_kuhy(before: set[str], parts: tuple[Part, ...]) -> list[Part]:
    return [p for p in parts if p.actionable and p.key not in before and lane.of_text(p.body) == lane.KUHY]


def refresh(d: Driver) -> str:
    """Take the card's fresh parts into the drive; return the switch note ("" when nothing new of kuhy's)."""
    if not d.item.parts:
        return ""
    run_dir = d.ctx.run_dir
    try:
        task = cast("Client", d.ctx.client).get_task(run_dir.name)  # the engine's client reads cards too
    except TodoError as exc:  # the todo app is away for a moment: keep the parts the drive has
        log.warning("%s: parts not refreshed: %s", run_dir.name, exc)
        return ""
    before = {str(row["key"]) for row in read_json(run_dir / files.PARTS) or []}
    d.item = task.item
    files.snapshot(run_dir, task.item, task.priority)
    fresh = _new_kuhy(before, task.item.parts)
    return SWITCH.format(parts="; ".join(f"[{p.key}] {p.title}" for p in fresh)) if fresh else ""


def before_turn(d: Driver, role: str) -> bool | str:
    """Refresh an implement turn's parts and return the turn's one-shot nudge (the switch note joins it)."""
    nudge: bool | str = d.state.extra.pop("nudge", False)
    switch = refresh(d) if role == IMPLEMENT else ""
    if not switch or nudge is True:  # the switch note asks for the work and the tag line itself
        return switch or nudge
    return f"{nudge}\n{switch}" if nudge else switch
