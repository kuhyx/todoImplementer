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

from todoimpl.asks import carry, store
from todoimpl.asks.carry import is_approve
from todoimpl.asks.parse import parse_asks

from . import crithash
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

STALE = (
    "(runner) kuhy approved {ids} before its text in plan.md changed, so that approve no longer counts. Show "
    "him the deliverable again and end with `A:` and an `ask` block holding, per criterion, "
    "`choice {first}: <question> | *approve | change`."
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
    """Return kuhy's own records of this cycle by ask id: clicked (never auto-adopted), this cycle's.

    asks.json outlives the cycles of a repo card (it holds his manual-part answers too) and criterion ids come
    back, so a record of an earlier cycle belongs to an earlier deliverable. A record with no cycle is
    judged by `_fresh` alone.
    """
    items, now = store.load(run_dir)["items"], carry.cycle(run_dir)
    return {
        ask_id: record
        for ask_id, record in items.items()
        if record.get("state") in ("answered", "approved", "rejected") and record.get("cycle", now) == now
    }


def _fresh(run_dir: Path, record: dict[str, Any], crit: str | None) -> bool:
    """Return True when the record answers the criterion as it reads now (T2462).

    A record with a hash counts while the criterion still hashes the same, however often the plan was
    rewritten around it. A record clicked before hashes were stamped falls back to: newer than the plan.
    """
    if "crit" in record:
        return record["crit"] is not None and record["crit"] == crit
    return float(record.get("at") or 0) >= _planned(run_dir)


def _stale(run_dir: Path, cid: str) -> dict[str, Any] | None:
    """Return kuhy's approve of this cycle on the criterion's ask when the criterion changed since."""
    record = _his(run_dir).get(cid.lower())
    crit = crithash.from_file(run_dir / "plan.md", cid.lower())
    if record is None or not _approves(record) or "crit" not in record or _fresh(run_dir, record, crit):
        return None
    return record


def _approves(record: dict[str, Any]) -> bool:
    return record.get("state") == "approved" or (
        record.get("state") == "answered" and is_approve(record.get("answer"))
    )


def approved(run_dir: Path, cid: str, *, sole: bool = False) -> bool:
    """Return True when kuhy approved the criterion this cycle, in any form the board records (T2376).

    The ask named after it (`c<n>`): a choice answered with an option that starts with `approve`
    (`approve once the gaps are filled` too) or a screenshot he approved. When it is the plan's only `(kuhy)`
    criterion, his approve on a choice of any id counts too: the review ask the session showed him. Either
    counts only while the criterion reads as it did at his click (T2462).
    """
    his, crit = _his(run_dir), crithash.from_file(run_dir / "plan.md", cid.lower())
    if (own := his.get(cid.lower())) is not None:
        return _approves(own) and _fresh(run_dir, own, crit)
    return sole and any(
        r.get("state") == "answered" and _approves(r) and _fresh(run_dir, r, crit) for r in his.values()
    )


def _said(run_dir: Path, cid: str) -> str | None:
    """Return kuhy's own answer on the criterion's ask this cycle, if it still answers the criterion."""
    record = _his(run_dir).get(cid.lower())
    if record is None or not _fresh(run_dir, record, crithash.from_file(run_dir / "plan.md", cid.lower())):
        return None
    return str(record.get("answer") or record.get("state"))


def _reopen(run_dir: Path, ids: list[str]) -> None:
    """Drop the stale approves so their asks show as buttons again."""
    data = store.load(run_dir)
    for cid in ids:
        data["items"].pop(cid.lower(), None)
    store.save(run_dir, data)


def _restale(d: Driver, missing: list[str]) -> list[str]:
    """Return the criteria whose approve went stale: just now (the record is dropped) or on an earlier pass."""
    now = [cid for cid in missing if _stale(d.ctx.run_dir, cid) is not None]
    _reopen(d.ctx.run_dir, now)
    earlier = [
        cid
        for cid in d.state.extra.get("stale", [])
        if cid in missing and cid not in now and _said(d.ctx.run_dir, cid) is None
    ]
    if stale := now + earlier:
        d.state.extra["stale"] = stale
    return stale


def _reask(d: Driver, stale: list[str]) -> str:
    """Show the stale asks as buttons again: the newest reply holds them, else the session asks once more."""
    asked = {a.id for a in parse_asks(str(d.state.extra.get("last_reply", "")))}
    if not d.state.extra.get("stale_nudged") and not all(cid.lower() in asked for cid in stale):
        d.state.extra["stale_nudged"] = True
        d.state.extra["nudge"] = STALE.format(ids=", ".join(stale), first=stale[0].lower())
        return "live_check"
    raise NeedsYouError(f"{', '.join(stale)}: approved before the plan changed; re-approve", "claude_action")


def owed(d: Driver, criteria: list[str]) -> str | None:
    """Return None once every `(kuhy)` criterion is approved; else send the session back once, then raise.

    Once kuhy answered the criterion's ask and it still is no approve, Needs you says so at once: the session
    never asks him the same thing again (T2376).
    """
    extra, ids = d.state.extra, kuhy_ids(criteria)
    missing = [cid for cid in ids if not approved(d.ctx.run_dir, cid, sole=len(ids) == 1)]
    if not missing:
        for key in ("approval_nudges", "stale", "stale_nudged"):
            extra.pop(key, None)
        return None
    if stale := _restale(d, missing):
        return _reask(d, stale)
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
