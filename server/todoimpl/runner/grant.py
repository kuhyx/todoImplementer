"""Backstop for the standing grant: an `A:` that only asks permission is answered once, not parked on kuhy.

Deterministic on purpose (regex over the concrete ask, no LLM). The session is resumed once per stage with a
fixed message, the way permit.py reruns a stage after learning a rule; a second permission ask parks the card.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.board.ask import concrete_ask

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

GRANTED = (
    "(runner) Granted: you have kuhy's standing permission to do this yourself (commit, push from your "
    "worktree, tags, installers, scripts, marker files, long runs via systemd-run). Do it now and carry on."
)
MAX_GRANTS = 1
NOT_FOR = ("spec", "plan")  # these stages edit nothing, so there is nothing to grant
PERMISSION_ASK = re.compile(
    r"\bok me\b|\bapprov(?:e|al)\b|\bpermission\b|\bmay i\b|\bauthori[sz](?:e|ation)\b|\bgo-?ahead\b"
    r"|\b(?:should|can|could|shall) i\b.{0,40}\b(?:commit|push|merge|tag|install|run|deploy)\b"
    r"|\bwhether to (?:commit|push|merge)\b|\bpress retry\b|\bsend a `?long:"
    r"|\bwrite\b.{0,80}\bby hand\b|\brun\b.{0,80}\byourself\b"
    r"|\bafter the server (?:commits|tags|ships|pushes)\b|\boff-limits\b|\bnot allowed\b|\bforbidden\b"
    r"|\b(?:editing|touching) main\b",
    re.IGNORECASE,
)


def is_permission_ask(ask: str) -> bool:
    """Return True when the ask is about being allowed to act (commit, push, run), not a real decision."""
    return PERMISSION_ASK.search(ask) is not None


def auto_grant(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Return True to resume the session once with the grant after a permission-only `A:` (T1863)."""
    st = driver.state
    if res.tag != "A":
        st.extra.pop("ask_grants", None)  # the turn moved on: the next permission ask gets its own grant
        return False
    ask = concrete_ask(st) or ""
    if stage in NOT_FOR or st.extra.get("waiting_phone") or res.is_error or not is_permission_ask(ask):
        return False
    given: dict[str, int] = st.extra.setdefault("ask_grants", {})
    if given.get(stage, 0) >= MAX_GRANTS:
        return False
    given[stage] = given.get(stage, 0) + 1
    st.extra["granted_note"] = GRANTED
    driver.activity(f"auto-granted, the session resumes: {ask}")
    return True
