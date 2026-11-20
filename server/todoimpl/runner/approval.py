"""Criteria only kuhy can tick (T2362): his judgement or approval of a deliverable gates Ship.

When a spec answer puts kuhy in the loop on a deliverable (a mail, message, post, design), the plan
writes that criterion as `Cn. (kuhy) ...` (prompts/texts.py). The session's own tick never counts for
it: only an answer kuhy clicked in the board this cycle (asks.json, written by the server) does: an option
starting with `approve` on the ask `cn`, or his Approve on a screenshot `cn` (`approved`, T2376). An
auto-adopted answer or any other option is no approval. Until then the run never reaches Checks, never
ships partly with a follow-up and never defers the criterion: the session is told once to put the
deliverable in an ask, then the card is Needs you. Once kuhy answered that ask with no approve, Needs you
says so at once instead of asking him again.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from todoimpl.asks import store
from todoimpl.asks.carry import is_approve

from .files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path

    from .pipeline import Driver

MARK = re.compile(r"^\s*\(kuhy\)", re.IGNORECASE)
MAX_NUDGES = 1
NUDGE = (
    "(runner) {ids} is kuhy's to tick, not yours: no tick of yours counts and the run cannot ship "
    "without his answer. Put the deliverable itself in your reply (its full text and the gaps left), "
    "say whether you can do the outward step (send, post) yourself, and end with `A:` and an `ask` "
    "block holding, per criterion, `choice {first}: <question> | *approve | change`. After `approve`, "
    "do the outward step and tick it."
)


def kuhy_ids(criteria: list[str]) -> list[str]:
    """Return the ids of the plan criteria marked `(kuhy)`."""
    return [f"C{n}" for n, text in enumerate(criteria, 1) if MARK.match(text)]


def _planned(run_dir: Path) -> float:
    """Return when this cycle's plan was written: a new cycle deletes plan.md, the plan stage rewrites it."""
    try:
        return (run_dir / "plan.md").stat().st_mtime
    except OSError:
        return 0.0


def _his(run_dir: Path) -> dict[str, dict[str, Any]]:
    """Return kuhy's own records of this cycle by ask id: clicked (never auto-adopted), newer than the plan.

    asks.json outlives the cycles of a repo card (it holds his manual-part answers too) and criterion ids come
    back, so an answer older than the plan belongs to an earlier deliverable.
    """
    planned = _planned(run_dir)
    items = store.load(run_dir)["items"]
    return {
        ask_id: record
        for ask_id, record in items.items()
        if record.get("state") in ("answered", "approved", "rejected")
        and float(record.get("at") or 0) >= planned
    }


def _approves(record: dict[str, Any]) -> bool:
    return record.get("state") == "approved" or (
        record.get("state") == "answered" and is_approve(record.get("answer"))
    )


def approved(run_dir: Path, cid: str, *, sole: bool = False) -> bool:
    """Return True when kuhy approved the criterion this cycle, in any form the board records (T2376).

    The ask named after it (`c<n>`): a choice answered with an option that starts with `approve`
    (`approve once the gaps are filled` too) or a screenshot he approved. When it is the plan's only `(kuhy)`
    criterion, his approve on a choice of any id counts too: the review ask the session showed him.
    """
    his = _his(run_dir)
    if (own := his.get(cid.lower())) is not None:
        return _approves(own)
    return sole and any(r.get("state") == "answered" and _approves(r) for r in his.values())


def _said(run_dir: Path, cid: str) -> str | None:
    """Return kuhy's own answer on the criterion's ask this cycle, if he gave one."""
    record = _his(run_dir).get(cid.lower())
    return None if record is None else str(record.get("answer") or record.get("state"))


def owed(d: Driver, criteria: list[str]) -> str | None:
    """Return None once every `(kuhy)` criterion is approved; else send the session back once, then raise.

    Once kuhy answered the criterion's ask and it still is no approve, Needs you says so at once: the session
    never asks him the same thing again (T2376).
    """
    extra, ids = d.state.extra, kuhy_ids(criteria)
    missing = [cid for cid in ids if not approved(d.ctx.run_dir, cid, sole=len(ids) == 1)]
    if not missing:
        extra.pop("approval_nudges", None)
        return None
    if said := [f"{cid.lower()}: {a}" for cid in missing if (a := _said(d.ctx.run_dir, cid)) is not None]:
        msg = (
            f"{', '.join(missing)} is not approved: you answered {'; '.join(said)}, and no approve came after"
        )
        raise NeedsYouError(msg, "claude_action")
    ids_text = ", ".join(missing)
    nudges = int(extra.get("approval_nudges", 0))
    if nudges >= MAX_NUDGES:
        msg = f"{ids_text} needs your approval in the board ask; the session did not ask for it"
        raise NeedsYouError(msg, "claude_action")
    extra["approval_nudges"] = nudges + 1
    extra["nudge"] = NUDGE.format(ids=ids_text, first=missing[0].lower())
    return "live_check"
