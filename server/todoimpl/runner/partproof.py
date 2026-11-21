"""A ticked part no passed live row names goes back to the live check, never to kuhy (T2467).

T2460 made Ship refuse such a part. The refusal rested in Needs you with work only a session can do (card
a5f05d17-0: the session had cut a heavy build to 19-29 s slices, the live check deferred that part's row
"after ship", and kuhy was told to "check it live or untick it", which he has no way to do). Now the part
goes back to the live check, `MAX_ROUNDS` times per Start: one turn that checks only the named parts and
writes only their rows, which the board merges into the stored report. After that the board unticks the
part itself and ships the proven ones; the part stays open for the next cycle. Only a run with no proven
part left rests, with Retry as its one step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.repotask import files

from .files import NeedsYouError
from .parsing import parse_live

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState
    from todoimpl.repotask.model import Part

    from .pipeline import Driver

MAX_ROUNDS = 2  # proof rounds of the live check per Start
ROUNDS = "proof_rounds"  # state.extra: the rounds used
BRIEF = "proof_brief"  # state.extra: the running round's brief, until its report is settled
NONE_TICKED = "No part is ticked, so Ship would close nothing: tick the finished parts, then Retry"


def _said(part: Part, rows: list[dict[str, object]]) -> str:
    """One line for a part: what each of its rows said, or that none names it."""
    own = [
        f"{row['criterion']} {'deferred' if row['deferred'] else 'not done'} ({row['note']})"
        for row in rows
        if row["part"] == part.key
    ]
    return f"[{part.key}] {part.title}: " + ("; ".join(own) if own else "no criterion names it")


def owed(d: Driver, report: str) -> str | None:
    """Return `live_check` while a ticked part lacks its proof and a round is left; None when Ship may go.

    Past the rounds the unproven parts are unticked here. Raises NeedsYouError when nothing ticked is left.
    """
    if not d.item.parts:  # a plain card: nothing to tick
        return None
    st, run_dir = d.state, d.ctx.run_dir
    ticked = files.ticked(run_dir, d.item)
    if not ticked:
        raise NeedsYouError(NONE_TICKED, "run_failed")
    rows = parse_live(report)
    unproven = files.unproven(run_dir, d.item, rows)
    if not unproven:
        return None
    said = "; ".join(_said(part, rows) for part in unproven)
    used = int(st.extra.get(ROUNDS, 0))
    if used < MAX_ROUNDS:
        st.extra.update({ROUNDS: used + 1, BRIEF: said})
        d.activity(f"ship waits, the live check proves {len(unproven)} part(s) ({used + 1}/{MAX_ROUNDS})")
        return "live_check"
    if len(unproven) == len(ticked):
        msg = f"The live check proved no ticked part in {MAX_ROUNDS} more rounds ({said}): "
        raise NeedsYouError(msg + "Retry runs the live check again", "run_failed")
    files.untick(run_dir, [part.key for part in unproven])
    d.activity(f"left open, no live proof in {MAX_ROUNDS} more rounds: {said}")
    return None


def ask(st: RunState, redo: str) -> tuple[str, str]:
    """Return a live-check turn's brief and prompt: the checklist redo, a proof round, or the plain stage."""
    if redo:
        return redo, "live_checklist"
    brief = str(st.extra.get(BRIEF, ""))
    return brief, "live_proof" if brief else ""


def settled(st: RunState, report_file: Path, report: str) -> str:
    """Return the report to judge: a proof round wrote only its parts' rows, the stored one keeps the rest."""
    if BRIEF not in st.extra:
        return report
    del st.extra[BRIEF]
    whole = merged(str((st.live_check or {}).get("report_md", "")), report)
    report_file.write_text(whole, encoding="utf-8")
    return whole


def _criterion(line: str) -> str | None:
    rows = parse_live(line)
    return str(rows[0]["criterion"]).upper() if rows else None


def merged(old: str, new: str) -> str:
    """Return the stored report with each row the proof round wrote again replaced; new rows go last."""
    fresh = {cid: line for line in new.splitlines() if (cid := _criterion(line))}
    kept = [fresh.pop(cid, line) if (cid := _criterion(line)) else line for line in old.splitlines()]
    return "\n".join([*kept, *fresh.values()])
