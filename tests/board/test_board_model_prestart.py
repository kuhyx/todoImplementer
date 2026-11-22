"""The model picker is the one place a card shows its model, and it is offered before Start (T2477, T2478)."""

from __future__ import annotations

from dataclasses import replace

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl import modelpick
from todoimpl.board import board
from todoimpl.board.card import build_card
from todoimpl.board.types import MANUAL_REASON

FABLE, OPUS, SONNET, HAIKU = (m.id for m in modelpick.MODELS)


def _picker(card: dict[str, object]) -> dict[str, object] | None:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next((a for a in actions if a["id"] == "model"), None)


def test_t2477_no_card_carries_a_model_label_beside_the_picker() -> None:
    card = build_card(Note(), run(extra={modelpick.PIN: FABLE, "last_model": "opus"}), ctx())
    assert "model" not in card
    validate("board", {**board.build_board([Note()], {}, ctx(), "b"), "tasks": [card]})


def test_t2478_a_backlog_card_offers_the_picker_pressed_on_the_default() -> None:
    card = build_card(Note(), None, ctx())
    picker = _picker(card)
    assert picker is not None
    assert (picker["enabled"], picker["value"]) == (True, OPUS)
    assert picker["choices"] == modelpick.choices()
    validate("common", card, "task_card")


def test_t2478_a_backlog_card_presses_its_saved_pick() -> None:
    picked = replace(ctx(), pin=lambda card: SONNET if card == "c59d2588-0" else None)
    picker = _picker(build_card(Note(), None, picked))
    assert picker is not None
    assert picker["value"] == SONNET


def test_t2478_a_cancelled_card_presses_its_pin_else_the_default_never_its_last_model() -> None:
    pinned = _picker(build_card(Note(), run(stage="cancelled", extra={modelpick.PIN: HAIKU}), ctx()))
    assert pinned is not None
    assert (pinned["enabled"], pinned["value"]) == (True, HAIKU)
    plain = _picker(build_card(Note(), run(stage="cancelled", extra={"last_model": "sonnet"}), ctx()))
    assert plain is not None
    assert plain["value"] == OPUS  # Restart runs unpinned on the default, whatever the last turn ran on


def test_t2478_a_yours_note_that_can_start_offers_the_picker() -> None:
    picker = _picker(build_card(Note(repo=None), None, ctx()))
    assert picker is not None
    assert picker["enabled"] is True


def test_t2478_no_picker_when_start_is_disabled() -> None:
    manual = build_card(Note(title="MANUAL WORK REQUIRED: plug the cable", repo=None), None, ctx())
    assert manual["actions"][0]["reason"] == MANUAL_REASON
    assert _picker(manual) is None
    missing = build_card(Note(repo="/nowhere"), None, ctx(missing="/nowhere"))
    assert missing["actions"][0]["enabled"] is False
    assert _picker(missing) is None


def test_t2478_no_picker_on_a_done_card() -> None:
    assert _picker(build_card(Note(status="done"), run(stage="shipped"), ctx())) is None
