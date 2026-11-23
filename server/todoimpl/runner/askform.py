"""A bare `A:` goes back to its session once, to become buttons or an exact step (T2048).

A Needs-you card must be answerable at a glance (DOCS-asks.md): a decision is a `choice` with a recommended
option, a step for kuhy a `command` or `screenshot`. A turn that ends on `A:` with no valid `ask` block
resumes the session with a fixed note (no LLM), once per stage and twice per run, like `grant.py`. The note
also hands every phone, device and E2E check back to Claude; a phone wait the phone stage tracks
(`waiting_phone`) is left to it. An ask block of phone work and runnable commands only goes back too, with
the phone note and its own budget (`devicework.py`, T2522).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.asks.parse import diagnose, parse_asks
from todoimpl.errors.marks import unattended

from .devicework import claude_work, send_back
from .grant import NOT_FOR
from .phone import asks_for_hands

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

FORM = (
    "(runner) Your `A:` reached kuhy as plain text with no buttons, and prose is not an answer he can give. "
    "First: a phone, device, emulator, airplane-mode or E2E check is yours, never kuhy's: run it "
    "yourself on the Pixel or emulator now, and ask only if adb shows no device. "
    "Anything else you can do yourself: do it. "
    "If kuhy must act, end on `A:` plus one fenced ```ask block, one line per item: "
    "a decision is `choice <id>: <title> | option | *recommended | option | risk=reversible` "
    "(2 to 8 options, exactly one `*`; one `choice` line per decision); "
    "a step he must take is `command <id>: <exact command>` "
    "or `screenshot <id>: <what to check> | shots/<name>.png`. "
    "Anything he must look at goes into the task itself (a `screenshot` line, a `choice`), never "
    "`open <path>`; a page that must be opened gets its full absolute URL. "
    "Name the exact step, never `check it`, `confirm it` or `decide`."
)
REJECTED = "(runner) Your ask block was rejected, so kuhy saw none of it. The line that broke it:\n"
MAX_FORMS = 1  # per stage; the count clears when a turn ends on anything but `A:`
MAX_FORMS_RUN = 2  # per run, cleared by Start, Retry and a note from kuhy
RUN_KEY = "ask_form_total"


def needs_form(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Return True to resume the session after an `A:` with no ask block, or one of phone work only."""
    st = driver.state
    if res.tag != "A":
        st.extra.pop("ask_forms", None)
        return False
    reply = str(st.extra.get("last_reply", ""))
    if stage in NOT_FOR or st.extra.get("waiting_phone") or res.is_error or res.denials:
        return False
    asks = parse_asks(reply)
    if asks and claude_work(asks):  # phone work kuhy cannot be handed, whatever the A: line says (T2522)
        return not unattended(st) and send_back(driver)
    if not reply.strip() or asks or unattended(st) or asks_for_hands(reply):
        return False  # a tap or plug-in ask has its own nudge (phone.py, T1827)
    given: dict[str, int] = st.extra.setdefault("ask_forms", {})
    total = int(st.extra.get(RUN_KEY, 0))
    if given.get(stage, 0) >= MAX_FORMS or total >= MAX_FORMS_RUN:
        return False
    given[stage] = given.get(stage, 0) + 1
    st.extra[RUN_KEY] = total + 1
    problem = diagnose(reply)
    st.extra["granted_note"] = FORM if problem is None else f"{REJECTED}{problem}\n\n{FORM}"
    driver.save()  # before the turn starts: a restart during it must not send the same ask back twice
    driver.activity("the A: has no ask block, the session resumes to write one")
    return True
