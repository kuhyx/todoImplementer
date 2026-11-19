"""A card's model picker and the model its turns run on (T2218): the server offers both, the page draws."""

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl import modelpick
from todoimpl.board import board
from todoimpl.board.card import build_card

FABLE = modelpick.MODELS[0].id


def _picker(card: dict[str, object]) -> dict[str, object] | None:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next((a for a in actions if a["id"] == "model"), None)


def test_t2218_a_run_offers_the_picker_with_its_pin_and_shows_the_model() -> None:
    card = build_card(Note(), run(stage="failed", extra={modelpick.PIN: FABLE, "last_model": "opus"}), ctx())
    picker = _picker(card)
    assert picker is not None
    assert (picker["enabled"], picker["value"], picker["label"]) == (True, FABLE, "Model")
    assert picker["choices"] == modelpick.choices()
    assert card["model"] == FABLE  # the pin wins over the latest turn's model
    validate("board", {**board.build_board([Note()], {}, ctx(), "b"), "tasks": [card]})


def test_t2218_without_a_pin_the_picker_says_default_and_the_card_its_latest_model() -> None:
    card = build_card(Note(), run(extra={"last_model": "opus"}), ctx(live=("c59d2588-0",)))
    picker = _picker(card)
    assert picker is not None
    assert (picker["enabled"], picker["value"]) == (True, modelpick.DEFAULT)
    assert card["model"] == "opus"
    assert "model" not in build_card(Note(), run(), ctx())  # no turn ran yet


def test_t2218_no_picker_once_the_run_ended_or_while_it_ships() -> None:
    assert _picker(build_card(Note(), None, ctx())) is None
    assert _picker(build_card(Note(), run(stage="shipped"), ctx())) is None
    closing = run(stage="checks", auto_start={"reason": "done_check", "passed_at": 1.0})
    assert _picker(build_card(Note(), closing, ctx())) is None
    shipping = _picker(build_card(Note(), run(stage="shipping"), ctx()))
    assert shipping is not None
    assert (shipping["enabled"], shipping["reason"]) == (False, "shipping is in progress")
