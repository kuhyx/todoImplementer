"""The card's tier badges: cheap from the note until a run decided, then what the run recorded."""

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl.board import board
from todoimpl.board.card import build_card


def tier(note: Note, **extra: object) -> dict[str, bool]:
    card = build_card(note, run(extra=extra) if extra else None, ctx())
    validate("board", {**board.build_board([note], {}, ctx(), "b"), "tasks": [card]})
    badges: dict[str, bool] = card["tier"]
    return badges


def test_ordinary_card_has_no_badge() -> None:
    assert tier(Note()) == {"cheap": False, "free": False, "escalated": False}


def test_cheap_by_title_or_body_before_any_run() -> None:
    cheap = {"cheap": True, "free": False, "escalated": False}
    assert tier(Note(title="text-free (textgate-rework)")) == cheap
    assert tier(Note(body="x\nTier: cheap")) == cheap


def test_run_record_wins_over_the_note() -> None:
    assert tier(Note(body="Tier: cheap"), tier="normal")["cheap"] is False
    assert tier(Note(), tier="cheap")["cheap"] is True


def test_free_badge_follows_the_servers_verdict() -> None:
    assert tier(Note(), tier="cheap", free_models=True) == {"cheap": True, "free": True, "escalated": False}
    assert tier(Note(), tier="cheap", free_models=False)["free"] is False


def test_escalated_card_shows_escalated_and_not_free() -> None:
    got = tier(Note(), tier="cheap", free_models=True, escalated=True)
    assert got == {"cheap": True, "free": False, "escalated": True}
