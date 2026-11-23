"""Server start parses again the questions of a card that waits in spec_wait with none stored (T2526).

A reply an older parser could not split left the card on the free "Claude asks" view; the parser that fixed
it runs again over the stored reply, so the card gets its question cards, Send answers and Spec OK back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.board import state as store

from .files import write_json
from .parsing import parse_questions

if TYPE_CHECKING:
    from pathlib import Path

    from todoimpl.board.state import RunState


def questions(run_dir: Path, st: RunState) -> None:
    """Store the cards of the stored reply of a spec_wait run that has none; no cards found, no write."""
    if st.stage != "spec_wait" or st.spec_questions:
        return
    cards = parse_questions(str(st.extra.get("last_reply", "")))
    if not cards:
        return
    st.spec_questions = cards
    write_json(run_dir / "questions.json", [vars(q) for q in cards])
    store.save(run_dir, st)
