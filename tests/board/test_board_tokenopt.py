"""A card whose run the reset watch started carries `auto: tokenopt`; state.json documents the mark."""

import json
from pathlib import Path
from typing import Any

import pytest
from board_helpers import Note, ctx, run
from contract_lib import validate
from jsonschema import ValidationError
from todoimpl.board import board
from todoimpl.board.card import build_card

STATE: dict[str, Any] = json.loads(
    (Path(__file__).parents[1] / "fixtures" / "state.json").read_text(encoding="utf-8")
)
MARK = {"tokenopt": {"key": "2027-01-15T08:00:00+00:00", "at": 1.0}}


def test_t2556_the_tokenopt_run_card_says_auto_tokenopt() -> None:
    card = build_card(Note(), run(extra=dict(MARK)), ctx())
    assert card["auto"] == "tokenopt"
    assert build_card(Note(), run(), ctx())["auto"] is None
    assert build_card(Note(), None, ctx())["auto"] is None
    validate("board", {**board.build_board([Note()], {}, ctx(), "b"), "tasks": [card]})


def test_t2556_state_json_with_the_mark_fits_the_contract() -> None:
    validate("state", {**STATE, **MARK})
    bad = {**STATE, "tokenopt": {"at": 1.0}}
    with pytest.raises(ValidationError):
        validate("state", bad)
