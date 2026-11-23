"""A note kuhy sends while a card ships reopens it on the same session once the ship is done (T2528).

kuhy (2026-11-23): Send to Claude takes a note on every open card; the note waits in `inbox.json` for the
next turn. A note sent while the card ships cannot ride a turn of that cycle, so when the ship is done the
card reopens in implement on the same session, the turn carries the note, and the card passes the gate and
ships again by itself. A failed ship keeps the note for the Retry turn, never starts one by itself.

The ship closed the card's parts, so the note becomes a new part of the repo's note (`add_task`): the card
has an open part again and the second ship closes it; the closed parts stay closed. A card that is not a
repo card (an umbrella, a note with no repo) keeps the note in the inbox for its next Start.

`inbox.fresh` beside the inbox marks notes sent since the last drain (`Engine.push_note`/`_drain`). Only
those reopen a card: an inbox older than this rule, left on a shipped run, never does. It is a file, not a
state key, because the shipping drive saves the state it loaded (as `whenfree.py`).
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from todoimpl.board import state as store
from todoimpl.board.parse import StateError
from todoimpl.todo_mcp.model import TodoError

from .files import read_json

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState

    from .scheduler import Scheduler

INBOX = "inbox.json"
FRESH = "inbox.fresh"
SHIP_STAGES = ("shipping", "gate")
MAX_TITLE = 80
NOTE = (
    "(runner) kuhy sent a note after this card shipped, so the card is open again on this session. The note "
    "is a new part titled {title!r}: do what it asks, tick that part, and add a criterion naming its key "
    "(`Cn [<key>]: ...`) to plan.md so the live check proves it. The parts that shipped stay closed."
)
log = logging.getLogger("todoimpl.runner")


def mark(run_dir: Path) -> None:
    """Mark the inbox as holding notes sent under this rule."""
    (run_dir / FRESH).touch()


def clear(run_dir: Path) -> None:  # noqa: D103
    (run_dir / FRESH).unlink(missing_ok=True)


def _notes(run_dir: Path) -> list[str]:
    return [str(n) for n in read_json(run_dir / INBOX) or []]


def retry_stage(run_dir: Path, stage: str) -> str:
    """Return implement instead of a ship again while a note waits: the Retry turn carries it."""
    return "implement" if stage in SHIP_STAGES and _notes(run_dir) else stage


def for_retry(st: RunState) -> bool:
    """Say whether a waiting note stays for the Retry turn: the run failed while it shipped."""
    return st.stage == "failed" and st.extra.get("failed_stage") in SHIP_STAGES


def _title(text: str) -> str:
    line = text.strip().splitlines()[0].strip()
    return line if len(line) <= MAX_TITLE else line[: MAX_TITLE - 1].rstrip() + "…"


def _say(sched: Scheduler, card: str, text: str) -> None:
    event = {"type": "activity", "at": sched.clock(), "kind": "system", "text": text, "tool": None}
    sched.bus.publish(card, event)


def reopen(sched: Scheduler, card: str, st: RunState) -> bool:
    """Reopen a shipped card on its session for the fresh notes; True when it did. Callers hold the lock."""
    run_dir = sched.root / card
    notes = _notes(run_dir)
    if st.stage != "shipped" or not notes or not (run_dir / FRESH).is_file():
        return False
    if not st.extra.get("repotask") or not st.repo:
        clear(run_dir)  # said once: the note waits in the inbox for the next Start
        _say(sched, card, "the note waits for the next Start: only a repo card reopens after its ship")
        return False
    text = "\n\n".join(notes)
    try:
        sched.client.add_task(st.repo, _title(text), text)
    except TodoError as exc:  # the next server start tries again (the mark stays)
        log.warning("late note of %s not added as a part: %s", card, exc)
        _say(sched, card, f"the note could not become a part, the card stays shipped: {exc}")
        return False
    st.stage = "implement"
    st.ship = st.checks = st.live_check = st.lesson = None
    st.self_check = []
    sched._route(st)  # noqa: SLF001 - the Scheduler's own note routing: error, tag, counters
    st.extra["granted_note"] = NOTE.format(title=_title(text))
    sched.save(card, st)
    sched.enqueue(card)
    _say(sched, card, "reopened on the same session: kuhy's note came after the ship")
    return True


def recover(sched: Scheduler) -> None:
    """At server start: reopen every card whose fresh note waited out a ship the deploy restart cut short."""
    with sched._cv:  # noqa: SLF001 - the Scheduler's own lock, as in whenfree.arm
        for flag in sorted(sched.root.glob(f"*/{FRESH}")):
            card = flag.parent.name
            try:
                st = store.load(flag.parent)
            except StateError:
                continue
            if st is not None and not sched.busy(card):
                reopen(sched, card, st)
