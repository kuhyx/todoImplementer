"""T2525: a Claude question no parser rule splits shows its full text on the Questions tab, never clipped."""

from __future__ import annotations

from typing import TYPE_CHECKING

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl.board import board

if TYPE_CHECKING:
    from pathlib import Path

LONG = (
    "What happens after a note queued during **shipping**: you accepted that a note sent while the card "
    "ships waits until the ship finishes. A finished ship makes the card Done, and Done cards take no notes, "
    "so the note would sit there forever unless the board reopens the card. Reopen it?"
)
REPLY = f"Checked the ship path.\n\n❓ {LONG}\nThe card keeps its session.\n➡️ Reopen it in implement.\n\nQ:\n"


def test_t2525_an_unparsed_question_keeps_its_full_text(tmp_path: Path) -> None:
    out = board.build_task(Note(), run(last_tag="Q", extra={"last_reply": REPLY}), tmp_path, ctx())
    validate("task", out)
    assert len(LONG) > 200
    assert out["asks"] == [
        {
            "id": "Q1",
            "title": "Claude asks",
            "body": f"{LONG}\nThe card keeps its session.",
            "recommendation": "Reopen it in implement.",
            "answer": None,
        }
    ]
    assert out["card"]["needs"]["text"].endswith("…")  # the one-line summary stays clipped


def test_t2525_a_plain_question_without_a_mark_is_the_text_after_the_tag(tmp_path: Path) -> None:
    reply = "Looked.\n\nQ: " + "which port should the scratch board use, " * 10 + "8790?"
    out = board.build_task(Note(), run(last_tag="Q", extra={"last_reply": reply}), tmp_path, ctx())
    assert [(a["body"], a["recommendation"]) for a in out["asks"]] == [(reply.split("Q: ", 1)[1], "")]


def test_t2525_an_empty_tag_falls_back_to_the_paragraph_before_it(tmp_path: Path) -> None:
    out = board.build_task(
        Note(), run(last_tag="Q", extra={"last_reply": "First.\n\nWhich port?\n\nQ:"}), tmp_path, ctx()
    )
    assert [a["body"] for a in out["asks"]] == ["Which port?"]


def test_t2525_no_reply_gives_no_card(tmp_path: Path) -> None:
    out = board.build_task(Note(), run(last_tag="Q", extra={"last_reply": "Q:"}), tmp_path, ctx())
    assert out["asks"] == []
