"""Criteria only kuhy can tick (T2362): his judgement or approval of a deliverable gates Ship.

When a spec answer puts kuhy in the loop on a deliverable (a mail, message, post, design), the plan
writes that criterion as `Cn. (kuhy) ...` (prompts/texts.py). The session's own tick never counts for
it: only an answer kuhy clicked in the board, the `approve` option of the ask `cn` (asks.json, written by
the server), does. An auto-adopted answer or any other option is no approval. Until then the run never
reaches Checks, never ships partly with a follow-up and never defers the criterion: the session is told
once to put the deliverable in an ask, then the card is Needs you.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.asks import store

from .files import NeedsYouError

if TYPE_CHECKING:
    from pathlib import Path

    from .pipeline import Driver

MARK = re.compile(r"^\s*\(kuhy\)", re.IGNORECASE)
APPROVE = "approve"
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


def approved(run_dir: Path, cid: str) -> bool:
    """Return True when kuhy himself clicked `approve` on the ask named after the criterion, this cycle.

    asks.json outlives the cycles of a repo card (it holds his manual-part answers too) and criterion ids come
    back, so an `approve` older than the plan belongs to an earlier deliverable.
    """
    record = store.load(run_dir)["items"].get(cid.lower()) or {}
    clicked = record.get("state") == "answered" and str(record.get("answer", "")).lower() == APPROVE
    return clicked and float(record.get("at") or 0) >= _planned(run_dir)


def owed(d: Driver, criteria: list[str]) -> str | None:
    """Return None once every `(kuhy)` criterion is approved; else send the session back once, then raise."""
    extra = d.state.extra
    missing = [cid for cid in kuhy_ids(criteria) if not approved(d.ctx.run_dir, cid)]
    if not missing:
        extra.pop("approval_nudges", None)
        return None
    ids = ", ".join(missing)
    nudges = int(extra.get("approval_nudges", 0))
    if nudges >= MAX_NUDGES:
        msg = f"{ids} needs your approval in the board ask; the session did not ask for it"
        raise NeedsYouError(msg, "claude_action")
    extra["approval_nudges"] = nudges + 1
    extra["nudge"] = NUDGE.format(ids=ids, first=missing[0].lower())
    return "live_check"
