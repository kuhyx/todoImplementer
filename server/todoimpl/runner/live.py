"""Settle a live check: rows against the plan's criteria, then pass, fix, accept partly, or ask kuhy."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from todoimpl.todo_mcp.model import TodoError

from . import retry
from .files import NeedsYouError
from .parsing import parse_criteria, parse_live

if TYPE_CHECKING:
    from todoimpl.board.state import RunState

    from .pipeline import Driver

MAX_LIVE_FIXES = 1
NO_CHECKLIST = (
    "Your last live check ended without the checklist. Do not re-run or re-verify anything: write the "
    "`- [x] Cn:` checklist now from what you already saw in this session. No background agent, no `R:`."
)
CRITERION_ID = re.compile(r"C\d+")
BOARD_URL = "http://127.0.0.1:8786"  # the loopback board (auth.DEFAULT_ORIGINS[0]); its #task= opens a card
STILL_OPEN = "The live check still saw criteria not done"
JUDGED = (STILL_OPEN, "follow-up note failed")  # errors the judge wrote; a rule change may undo them


@dataclass
class Verdict:
    """Live-check outcome per criterion id: done, open (id, why) and deferred to after the ship."""

    done: list[str] = field(default_factory=list)
    open: list[tuple[str, str]] = field(default_factory=list)
    deferred: list[str] = field(default_factory=list)
    seen: dict[str, str] = field(default_factory=dict)  # what the live check saw for each done criterion

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
            out.seen[cid] = str(row["note"])
        else:
            out.open.append((cid, str(row["note"])))
    return out


def _criterion(cid: str, criteria: list[str]) -> str:
    index = int(cid[1:]) - 1 if CRITERION_ID.fullmatch(cid) else -1
    text = criteria[index] if 0 <= index < len(criteria) else ""
    return f"- {cid}: {text}" if text else f"- {cid}"


def followup_body(found: Verdict, criteria: list[str], card: str, title: str) -> str:
    """Link the earlier card, then what it got done and what is left here, each with the plan text."""
    lines = [f"Earlier task: {title} ({card}) {BOARD_URL}/#task={card}", ""] if card else []
    if found.done:
        lines.append("Done in the earlier task:")
        for cid in found.done:
            lines += [_criterion(cid, criteria), f"  live check: {found.seen[cid]}"]
        lines.append("")
    lines.append("To do here:")
    for cid, note in found.open:
        lines += [_criterion(cid, criteria), f"  live check: {note}"]
    if found.deferred:
        lines += ["", "Deferred until after the ship:"]
        lines += [_criterion(cid, criteria) for cid in found.deferred]
    return "\n".join(lines)


def _followup(d: Driver, found: Verdict, criteria: list[str]) -> None:
    """Create the follow-up note once per run; its id is `extra["followup_id"]`."""
    extra = d.state.extra
    if extra.get("followup_id"):
        return
    title = f"{d.item.title} — rest: {', '.join(found.open_ids)}"
    try:
        body = followup_body(found, criteria, d.state.task_id, d.item.title)
        created = d.ctx.client.add_task(d.item.repo or "", title, body)
    except TodoError as exc:  # never Needs you: retry on the backoff, judging the stored report again
        extra["resettle"] = True
        raise retry.later(d.state, d.ctx.now(), f"follow-up note not added yet: {exc}") from exc
    extra["followup_id"] = created.id
    d.save()  # a restart right now must not add the note twice


def settle(d: Driver, report: str) -> str | None:
    """Return the next stage after a live check report (see DOCS-spec.md, live check)."""
    extra = d.state.extra
    rows = parse_live(report)
    if not rows:
        return _no_checklist(d)
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


def _no_checklist(d: Driver) -> str:
    """Miss 1: a checklist-only turn in the same session. Miss 2: the whole live check in a fresh session."""
    extra = d.state.extra
    misses = int(extra.get("live_redone", 0))
    if misses >= 2:  # noqa: PLR2004 - the two rungs above
        msg = "The live check wrote no checklist, not even when asked for it alone or in a fresh session"
        raise NeedsYouError(msg)
    extra["live_redone"] = misses + 1
    if misses == 0:
        extra["live_redo"] = NO_CHECKLIST
    else:
        extra.pop("live_redo", None)
        d.state.sessions.pop("implement", None)
    return "live_check"


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
    msg = f"{STILL_OPEN}: {', '.join(found.open_ids)}"
    raise NeedsYouError(msg)


def _report(st: RunState) -> str:
    return str((st.live_check or {}).get("report_md", ""))


def rejudgeable(st: RunState) -> bool:
    """Return True for a run the judge failed at live_check whose stored report has a done criterion."""
    judged = st.stage == "failed" and st.extra.get("failed_stage") == "live_check"
    if not judged or not any(mark in (st.error or "") for mark in JUDGED):
        return False
    return _has_done(_report(st))


def _has_done(report: str) -> bool:
    return any(row["done"] and not row["deferred"] for row in parse_live(report))


def rejudge(d: Driver) -> str | None:
    """Settle the stored report again with today's rules, spending no turn: the fix round counts as used."""
    extra = d.state.extra
    extra.pop("resettle", None)
    extra["live_fixes"] = MAX_LIVE_FIXES
    report = _report(d.state)
    if not _has_done(report):
        msg = f"{STILL_OPEN}: none done in the stored report"
        raise NeedsYouError(msg)
    return settle(d, report)
