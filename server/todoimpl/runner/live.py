"""Settle a live check: rows against the plan's criteria, then pass, fix, accept partly, or ask kuhy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todoimpl.todo_mcp.model import TodoError

from .files import NeedsYouError
from .parsing import parse_criteria, parse_live

if TYPE_CHECKING:
    from .pipeline import Driver

MAX_LIVE_FIXES = 1
NO_CHECKLIST = (
    "Your last live check ended without the checklist. Write the `- [x] Cn:` checklist yourself in this turn "
    "and finish it before you end. Do not delegate to a background agent and do not end with `R:`."
)
CRITERION_ID = re.compile(r"C\d+")


@dataclass
class Verdict:
    """Live-check outcome per criterion id: done, open (id, why) and deferred to after the ship."""

    done: list[str] = field(default_factory=list)
    open: list[tuple[str, str]] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)

    @property
    def open_ids(self) -> list[str]:
        """Ids of the criteria not done."""
        return [cid for cid, _ in self.open]


def verdict(rows: list[dict[str, object]], criteria: list[str]) -> Verdict:
    """Judge report rows; a plan criterion missing from the report counts as not done."""
    seen = {
        str(r["criterion"]).upper()
        if CRITERION_ID.fullmatch(str(r["criterion"]).upper())
        else str(r["criterion"]): r
        for r in rows
    }
    numbered = any(CRITERION_ID.fullmatch(key) for key in seen)
    expected = [f"C{i}" for i in range(1, len(criteria) + 1)] if numbered else []
    out = Verdict()
    for cid in [*expected, *(key for key in seen if key not in expected)]:
        row = seen.get(cid)
        if row is None:
            out.open.append((cid, "missing from the live check report"))
        elif row["deferred"]:
            out.deferred.append(cid)
        elif row["done"]:
            out.done.append(cid)
        else:
            out.open.append((cid, str(row["note"])))
    return out


def followup_body(found: Verdict, criteria: list[str]) -> str:
    """List every open criterion with its plan text and the live-check note."""
    lines = ["Left open by the live check:"]
    for cid, note in found.open:
        index = int(cid[1:]) - 1 if CRITERION_ID.fullmatch(cid) else -1
        text = criteria[index] if 0 <= index < len(criteria) else ""
        lines.append(f"- {cid}: {text}" if text else f"- {cid}")
        lines.append(f"  live check: {note}")
    return "\n".join(lines)


def _followup(d: Driver, found: Verdict, criteria: list[str]) -> None:
    """Create the follow-up note once per run; its id is `extra["followup_id"]`."""
    extra = d.state.extra
    if extra.get("followup_id"):
        return
    title = f"{d.item.title} — rest: {', '.join(found.open_ids)}"
    try:
        created = d.ctx.client.add_task(d.item.repo or "", title, followup_body(found, criteria))
    except TodoError as exc:
        msg = f"Live check left {', '.join(found.open_ids)} open and the follow-up note failed: {exc}"
        raise NeedsYouError(msg) from exc
    extra["followup_id"] = created.id


def settle(d: Driver, report: str) -> str | None:
    """Return the next stage after a live check report (see DOCS-spec.md, live check)."""
    extra = d.state.extra
    rows = parse_live(report)
    if not rows:
        if extra.get("live_redone"):
            msg = "The live check wrote no checklist twice: read the feed and send guidance"
            raise NeedsYouError(msg)
        extra["live_redone"] = 1
        extra["live_redo"] = NO_CHECKLIST
        return "live_check"
    extra.pop("live_redone", None)
    criteria = parse_criteria(d.plan_md())
    found = verdict(rows, criteria)
    if found.open:
        return _unfinished(d, report, found, criteria)
    extra.pop("live_fixes", None)
    extra.pop("partial", None)
    if found.deferred:
        extra["partial"] = {"done": found.done, "open": [], "deferred": found.deferred}
    return "checks"


def _unfinished(d: Driver, report: str, found: Verdict, criteria: list[str]) -> str | None:
    extra = d.state.extra
    fixes = int(extra.get("live_fixes", 0))
    if fixes < MAX_LIVE_FIXES:
        extra["live_fixes"] = fixes + 1
        extra["failure_tail"] = report
        return "implement"
    if found.done:
        _followup(d, found, criteria)
        extra["partial"] = {"done": found.done, "open": found.open_ids, "deferred": found.deferred}
        return "checks"
    if not extra.get("zero_done_retry"):
        extra["zero_done_retry"] = 1
        extra["failure_tail"] = report
        d.state.sessions.pop("implement", None)
        return "implement"
    why = f"The live check still saw criteria not done: {', '.join(found.open_ids)}"
    raise NeedsYouError(why)
