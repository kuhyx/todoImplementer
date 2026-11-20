"""An `A:` that asks only what kuhy already answered this cycle gets his answers back at once (T2376).

A session that asks a choice again keeps kuhy's answer (`asks/carry.py`), so when every ask of the reply
is already answered the card would rest in Needs you with nothing left to click. Instead the session
resumes with his answers in a fixed note (no LLM), twice per run (`answered_backs`); after that the card
rests as usual and shows the answers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.asks import store
from todoimpl.asks.view import is_open, told, work_asks
from todoimpl.errors.marks import unattended

from .grant import NOT_FOR

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

KEY = "answered_backs"
MAX_BACKS = 2
NOTE = (
    "(runner) kuhy already answered everything you just asked, earlier in this cycle, so the card showed "
    "him nothing new. Never ask these again; go on with his answers: {answers}"
)


def back(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Return True to resume the session with kuhy's answers when its `A:` asks nothing still open."""
    st = driver.state
    if res.tag != "A" or res.is_error or stage in NOT_FOR or unattended(st):
        return False
    asks = work_asks("", st)
    items = store.load(driver.ctx.run_dir, asks)["items"]
    backs = int(st.extra.get(KEY, 0))
    if not asks or any(is_open(items.get(a.id)) for a in asks) or backs >= MAX_BACKS:
        return False
    st.extra[KEY] = backs + 1
    st.extra["granted_note"] = NOTE.format(answers="; ".join(told(asks, items)))
    driver.save()  # before the turn starts: a restart during it must not send the same note twice
    driver.activity("the A: asks only what kuhy already answered, the session resumes with his answers")
    return True
