"""Phone work is Claude's (T2522): a check that needs phone interaction never rests on kuhy.

Card c96b7ce5-0 asked kuhy to "rate a few reviews on the phone" while a watcher ran, as an approve choice
plus the watcher's start command, because the plan had marked that check `(kuhy)`. Taps, ratings,
screenshots and timing measured on the device are a live check Claude drives itself (phone_slot, phone_vd,
adb, emulator). So a `(kuhy)` criterion that only asks for phone interaction is no approval gate, and an ask
block made only of such phone work and commands the session may run itself goes back to the session
(`askform.needs_form`). An approval of a deliverable stays kuhy's, even when it names the phone. Past its two
send-backs such an ask still never rests on kuhy (T2523): `to_claude` sends the card on to a fresh live check
(from implement) or settles the live check's report (an open phone check gets a fix turn), with the same note.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from todoimpl.asks.allow import NEVER_ADD, ROOT
from todoimpl.asks.parse import parse_asks
from todoimpl.errors.marks import unattended

if TYPE_CHECKING:
    from todoimpl.asks.parse import Ask

    from .pipeline import Driver
    from .stream import TurnResult

KEY = "phone_asks"  # its own budget: the bare-`A:` note may be what made the session write this block
MAX_RUN = 2  # per run, cleared by Start, Retry and Ship reruns (scheduler.RESET)

ACTION = re.compile(
    r"\b(?:rat(?:e|es|ed|ing|ings)|taps?|tapp(?:ed|ing)|swip(?:e|es|ed|ing)|scroll(?:s|ed|ing)?"
    r"|press(?:es|ed|ing)?|typ(?:e|es|ed|ing)|launch(?:es|ed|ing)?|install(?:s|ed|ing)?|open(?:s|ed|ing)?"
    r"|use|uses|used|using|play(?:s|ed|ing)?|measur(?:e|es|ed|ing)|screenshots?)\b",
    re.IGNORECASE,
)
ON_PHONE = re.compile(
    r"\b(?:on|from|with|in|via|using)\s+(?:the\s+|his\s+|your\s+|kuhy's\s+|a\s+|my\s+)?(?:real\s+)?"
    r"(?:phone|pixel|device)\b",
    re.IGNORECASE,
)
PHONE_THING = re.compile(r"\bphone\s+(?:reviews?|ratings?|taps?|checks?|screenshots?)\b", re.IGNORECASE)
APPROVAL = re.compile(r"\bapprov", re.IGNORECASE)
NOTE = (
    "(runner) Your ask hands kuhy phone work (rating, tapping, a screenshot or timing on the device) and "
    "commands you can run yourself: that is yours, never kuhy's. Run the commands, then drive the phone "
    "on your own slot: `~/.claude/scripts/phone_slot.sh acquire`, `phone_deploy.sh <app_dir> --release "
    "--slot`, `phone_vd.sh start <slot pkg>`, then tap/swipe/text/shot and time it from the device's own "
    "log; `phone_slot.sh release` at the end (slot data is sandboxed). Tick the criterion with what you saw. "
    "Without the Pixel in `adb devices`, stage phone_ready.json and end `A: phone: <one line>`. Ask kuhy "
    "only a real decision, as a `choice`."
)


def is_phone_work(text: str) -> bool:
    """Return True when the text asks for interaction with the phone, e.g. rating reviews on it."""
    return PHONE_THING.search(text) is not None or (
        ACTION.search(text) is not None and ON_PHONE.search(text) is not None
    )


def is_phone_check(criterion: str) -> bool:
    """Return True for a criterion that is phone interaction and not kuhy's approval of a deliverable."""
    return is_phone_work(criterion) and APPROVAL.search(criterion) is None


def _runnable(ask: Ask) -> bool:
    """Return True for a command the session may run itself: nothing root or in the never-add set."""
    command = ask.command or ""
    return ask.type == "command" and not NEVER_ADD.search(command) and not ROOT.search(command)


def claude_work(asks: list[Ask]) -> bool:
    """Return True when the ask block holds phone work and nothing but more of it or runnable commands."""
    phone = [a for a in asks if a.type != "command" and is_phone_work(a.title)]
    return bool(phone) and all(a in phone or _runnable(a) for a in asks)


def send_back(driver: Driver) -> bool:
    """Resume the session with the phone note, twice per run; past that the ask shows to kuhy."""
    extra = driver.state.extra
    done = int(extra.get(KEY, 0))
    if done >= MAX_RUN:
        return False
    extra[KEY] = done + 1
    extra["granted_note"] = NOTE
    driver.save()  # before the turn starts: a restart during it must not send the same note twice
    driver.activity("the ask hands kuhy phone work, the session resumes to do it itself")
    return True


def to_claude(driver: Driver, res: TurnResult) -> bool:
    """Return True when an `A:` would rest on an ask of phone work only: the next turn is Claude's (T2523).

    `askform.needs_form` sent it back to the session twice already. The next turn carries the phone note.
    Umbrella children and error runs, and a phone wait the phone stage tracks, keep their own paths.
    """
    st = driver.state
    if res.tag != "A" or unattended(st) or st.extra.get("waiting_phone"):
        return False
    if not claude_work(parse_asks(str(st.extra.get("last_reply", "")))):
        return False
    st.extra["nudge"] = NOTE
    driver.activity("the ask still hands kuhy phone work: a Claude turn does it instead")
    return True
