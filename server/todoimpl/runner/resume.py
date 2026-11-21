"""An `A:` whose resume text is only commands and waits Claude can do rests, then resumes (T2104).

Claude often ends a turn on `A: ... Resume by checking <unit>. When it finishes, run <script>.` while a build
it started is still running. Every step there is Claude's own, so the card must not sit in Needs you. The
runner rests the run in `paused_retry` on the retry ladder (1, 2, 5, 10 min, then 30 min) and the stage reruns
with the ask as its prompt. At most `MAX_RESUMES` passes per run (about 4 h); then the card parks as before.
Start, Retry and a note from kuhy clear the count. Deterministic on purpose (regex over the concrete ask).
Everything else an `A:` can mean stays with `grant.py` (a command or permission) or kuhy.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.board.ask import concrete_ask

from . import retry
from .grant import DECISION, KUHY_BLOCK, NOT_FOR
from .phone import READY, TRIED

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

KEY = "self_resumes"
MAX_RESUMES = 12
SHOWN = 110
RESUMED = (
    "(runner) Resume it yourself, nobody else will: the steps below are yours, you have kuhy's standing "
    "permission. If the unit or build is still running, wait for it inside this turn with event waits of at "
    "most 50 s each (`timeout 50 tail --pid=<its pid> -f /dev/null`, `inotifywait`, `gh run watch`; never "
    "start it again), never a sleep loop, then do the rest and carry on. Your last ask was:\n\n"
)
# What marks a wait or a resume line: "Resume by ...", "is-active", "when it finishes".
RESUME_ASK = re.compile(
    r"\bresume (?:by|with|once|when|after|from)\b|\bis-active\b"
    r"|\b(?:when|once|after) (?:it|the [\w-]+(?: [\w-]+)?) (?:finishes|is done|completes|ends)\b",
    re.IGNORECASE,
)
# Device and screen checks are Claude's own (phone_vd, phone_slot); only these need kuhy.
KUHY_ONLY = re.compile(
    r"\b(?:plug(?:ged)?(?: it)? in|plugging|unplug|audio|sound|listen|hear|speakers?|headphones?"
    r"|(?:click|press) (?:the )?(?:ship|retry)|ship (?:click|button)|passwords?|passcode|captcha|2fa|otp"
    r"|log ?in|credentials?|secrets?|tokens?|api keys?|you|your|me|note|reply|answer|approv\w*)\b"
    r"|(?<![.\w])kuhy(?![.\w])",  # not the `com.kuhy.slot8` package
    re.IGNORECASE,
)


def is_self_resume(ask: str, reply: str = "") -> bool:
    """Return True when the ask is a resume line of commands and waits and none of it is kuhy's."""
    if not ask.strip() or KUHY_BLOCK.search(reply):
        return False
    return RESUME_ASK.search(ask) is not None and not (KUHY_ONLY.search(ask) or DECISION.search(ask))


def rest(driver: Driver, res: TurnResult, stage: str) -> None:
    """Raise the retry that resumes the stage with the ask as its prompt, when `res` is a self-resumable `A:`.

    A phone wait the Pixel was already in for (`tried_attached`) is no cable ask, so it may rest; it stays
    (its `tried_attached` is how the next turn's `A: phone:` stays no cable ask too), the staged file goes. An
    untried one is the staged wait for kuhy's cable and is left alone. Anything else returns at once.
    """
    st = driver.state
    if res.tag != "A" or stage in NOT_FOR or res.is_error or res.denials:
        return
    wait = st.extra.get("waiting_phone")
    if wait and not (isinstance(wait, dict) and wait.get(TRIED)):
        return
    ask = concrete_ask(st) or ""
    if not is_self_resume(ask, str(st.extra.get("last_reply", ""))):
        return
    done = int(st.extra.get(KEY, 0))
    if done >= MAX_RESUMES:
        return
    st.extra[KEY] = done + 1
    (driver.ctx.run_dir / READY).unlink(missing_ok=True)
    st.extra["granted_note"] = RESUMED + ask
    st.last_tag = None
    driver.save()  # before the rest starts: a restart must not count this ask twice
    driver.activity(f"resuming by itself, no need for kuhy: {ask}")
    raise retry.RetryLaterError(driver.ctx.now() + retry.delay(done), f"resume: {ask[:SHOWN]}")
