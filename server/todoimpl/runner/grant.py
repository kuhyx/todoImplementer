"""Backstop for the standing grant: an `A:` that kuhy need not answer is answered by the runner, not parked.

That is a permission ask, or any ask for something Claude can run itself (a command, a deploy, a restart, a
write under ~). Deterministic on purpose (regex over the concrete ask, no LLM). The session is resumed once
per stage and twice per run with a fixed message, the way permit.py reruns a stage after learning a rule;
after that the card parks. Only kuhy's own asks never get the reply: a phone, audio or screen check, a
physical tap, a Ship click, a decision, an ask block with a choice or a screenshot.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.board.ask import concrete_ask

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

GRANTED = (
    "(runner) Granted: do it yourself, you have kuhy's standing permission (sudo, commit, push from your "
    "worktree, tags, deploy, restart, installers, scripts, writes under ~, long runs via systemd-run). "
    "Run it now, then rerun the card's checks and carry on. Answer `A:` again only for what needs kuhy's own "
    "hands (phone, audio, screen) or a decision."
)
MAX_GRANTS = 1  # per stage; the count clears when a turn ends on anything but `A:`
MAX_GRANTS_RUN = 2  # per run, cleared only by Start, Retry and a note from kuhy: A, R, A, R cannot loop
RUN_KEY = "ask_grant_total"
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
HUMAN_ONLY = re.compile(
    r"\b(?:phone|pixel|adb|plug(?:ged)?(?: it)? in|unplug|tap|touch|screen|screenshot|visual(?:ly)?|audio"
    r"|sound|listen|hear|speakers?|headphones?|(?:click|press) (?:the )?ship|ship (?:click|button)"
    r"|passwords?|passcode|captcha|2fa|otp|log ?in|sign ?in)\b",
    re.IGNORECASE,
)
DECISION = re.compile(
    r"\bwhich\b|\bdo you want\b|\bwould you like\b|\bprefer|\byour call\b|\byou decide\b|\bdecide\b"
    r"|\bchoose\b|\bpick\b|\bopinion\b|\bdecision\b",
    re.IGNORECASE,
)
KUHY_BLOCK = re.compile(r"^\s*(?:choice|screenshot)\s+\w+\s*:", re.IGNORECASE | re.MULTILINE)


def is_permission_ask(ask: str) -> bool:
    """Return True when the ask is about being allowed to act (commit, push, run), not a real decision."""
    return PERMISSION_ASK.search(ask) is not None


def is_autonomous_ask(ask: str, reply: str = "") -> bool:
    """Return True when Claude can do what the ask wants itself; kuhy's own kinds of ask never are."""
    if not ask.strip() or KUHY_BLOCK.search(reply):
        return False
    return is_permission_ask(ask) or not (HUMAN_ONLY.search(ask) or DECISION.search(ask))


def auto_grant(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Return True to resume the session with the grant after an `A:` kuhy need not answer (T1863, T2006)."""
    st = driver.state
    if res.tag != "A":
        st.extra.pop("ask_grants", None)  # the turn moved on: the next permission ask gets its own grant
        return False
    ask = concrete_ask(st) or ""
    reply = str(st.extra.get("last_reply", ""))
    if stage in NOT_FOR or st.extra.get("waiting_phone") or res.is_error:
        return False
    # An umbrella child sends every other `A:` back to implement with its own brief (bounce.again, T1952).
    autonomous = is_permission_ask(ask) if "umbrella_round" in st.extra else is_autonomous_ask(ask, reply)
    if not autonomous or (res.denials and not is_permission_ask(ask)):
        return False  # a refused tool call stays refused whatever a reply says
    given: dict[str, int] = st.extra.setdefault("ask_grants", {})
    total = int(st.extra.get(RUN_KEY, 0))
    if given.get(stage, 0) >= MAX_GRANTS or total >= MAX_GRANTS_RUN:
        return False
    given[stage] = given.get(stage, 0) + 1
    st.extra[RUN_KEY] = total + 1
    st.extra["granted_note"] = GRANTED
    driver.save()  # before the granted turn starts: a restart during it must not grant this ask again
    driver.activity(f"auto-granted, the session resumes: {ask}")
    return True
