"""T1816: a Claude question asked after the spec stage reaches the page as question cards (`asks`)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl.board import board
from todoimpl.board.state import SpecQuestion

if TYPE_CHECKING:
    from pathlib import Path

REPLY = """Looked at the cache code.

❓ **Q1** - **Failure vs. no-match**: A 429 now reads as no match.
Should it count as a failure?
➡️ Count it as a failure.

❓ **Q2** - **Pacing**: allow request pacing?
➡️ Yes, one request per second.

Q: allow request pacing so the cache repair can finish?
"""

ANSWERED = [SpecQuestion("Q1", "Scope", "Which?", "demo.py", "demo.py")]


def test_t1816_a_later_claude_question_is_sent_as_cards(tmp_path: Path) -> None:
    state = run(last_tag="Q", spec_questions=ANSWERED, extra={"last_reply": REPLY})
    out = board.build_task(Note(), state, tmp_path, ctx())
    validate("task", out)
    assert out["card"]["needs"]["kind"] == "claude_question"
    assert [(a["id"], a["title"], a["recommendation"], a["answer"]) for a in out["asks"]] == [
        ("Q1", "Failure vs. no-match", "Count it as a failure.", None),
        ("Q2", "Pacing", "Yes, one request per second.", None),
    ]
    assert out["asks"][0]["body"] == "A 429 now reads as no match.\nShould it count as a failure?"
    assert out["questions"] == [vars(ANSWERED[0])]


def test_t1816_no_cards_without_an_open_claude_question(tmp_path: Path) -> None:
    plain = run(last_tag="Q", extra={"last_reply": "Q: which port?"})
    asks = board.build_task(Note(), plain, tmp_path, ctx())["asks"]
    assert [a["body"] for a in asks] == ["which port?"]  # T2525: one full-text card
    done = run(last_tag="D", extra={"last_reply": REPLY})
    assert board.build_task(Note(), done, tmp_path, ctx())["asks"] == []
    assert board.build_task(Note(), None, tmp_path, ctx())["asks"] == []
