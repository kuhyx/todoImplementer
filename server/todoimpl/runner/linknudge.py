"""An `A:` that says "open /page" with no host goes back to its session to show it in the task (T2135).

kuhy cannot follow a bare route, and a page he must open is a step Claude can spare him: the picture or the
choice belongs in the task itself (DOCS-asks.md). `board/links.py` finds the route; this sends the session
back twice per run (`link_nudges`, cleared by Start, Retry and a note), with a fixed note and no LLM.
A reply whose `ask` block parses already shows buttons and is left alone, and `askform.needs_form` goes first,
so the two never set a note on the same turn.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.asks.parse import parse_asks
from todoimpl.board.ask import concrete_ask
from todoimpl.board.links import scan
from todoimpl.errors.marks import unattended

from .grant import NOT_FOR

if TYPE_CHECKING:
    from .pipeline import Driver
    from .stream import TurnResult

KEY = "link_nudges"
MAX_NUDGES = 2
NOTE = (
    "(runner) Your `A:` tells kuhy to open {routes}, with no host, so he has nothing to click. "
    "Anything he must look at goes into the task itself: take the screenshots or pictures yourself "
    "(headless browser, never his display), save them under shots/ in your run dir, and end on `A:` "
    "plus a fenced ```ask block with a `screenshot <id>: <what to check> | shots/<name>.png` line and a "
    "`choice <id>: <title> | opt | *recommended | opt | risk=reversible` line for the decision. "
    "If a page truly must be opened, write its full absolute URL (scheme, host, port, path)."
)


def needs_link(driver: Driver, res: TurnResult, stage: str) -> bool:
    """Return True to resume the session with the link note after an `A:` that names a page with no host."""
    st = driver.state
    if res.tag != "A" or stage in NOT_FOR or st.extra.get("waiting_phone") or res.is_error or res.denials:
        return False
    reply = str(st.extra.get("last_reply", ""))
    if unattended(st) or parse_asks(reply):
        return False
    done = int(st.extra.get(KEY, 0))
    bare = scan(concrete_ask(st) or "", reply).bare
    if not bare or done >= MAX_NUDGES:
        return False
    st.extra[KEY] = done + 1
    st.extra["granted_note"] = NOTE.format(routes=", ".join(f"`{route}`" for route in bare))
    driver.save()  # before the turn starts: a restart during it must not send the same note twice
    driver.activity(f"the A: names {', '.join(bare)} with no host, the session resumes to put it in the task")
    return True
