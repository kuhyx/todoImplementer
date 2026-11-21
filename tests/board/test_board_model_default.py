"""The picker presses the model the card runs on; the chip names it the same way (T2470).

The default model's button carries the default note (kuhy 2026-11-21: "sonnet" chip, "Default" pressed).
"""

import pytest
from board_helpers import Note, ctx, run
from todoimpl import modelpick
from todoimpl.board.card import build_card
from todoimpl.runner import claude

OPUS = "claude-opus-5-5"
SONNET = "claude-sonnet-5-5"


def _picker(card: dict[str, object]) -> dict[str, object]:
    actions = card["actions"]
    assert isinstance(actions, list)
    return next(a for a in actions if a["id"] == "model")


def test_t2470_the_picker_has_no_default_row_and_the_default_model_carries_the_note() -> None:
    rows = modelpick.choices()
    assert [r["id"] for r in rows] == [m.id for m in modelpick.MODELS]
    assert [r for r in rows if "note" in r] == [{"id": OPUS, "label": "Opus 5.5", "note": "default"}]
    assert modelpick.DEFAULT_MODEL == OPUS


@pytest.mark.parametrize(
    ("last", "pressed", "chip"), [("sonnet", SONNET, "Sonnet 5.5"), (SONNET, SONNET, "Sonnet 5.5")]
)
def test_t2470_without_a_pin_the_pressed_button_and_the_chip_name_the_model_that_ran(
    last: str, pressed: str, chip: str
) -> None:
    card = build_card(Note(), run(extra={"last_model": last}), ctx(live=("c59d2588-0",)))
    assert (_picker(card)["value"], card["model"]) == (pressed, chip)


def test_t2470_a_card_that_ran_no_turn_presses_the_default_model() -> None:
    assert _picker(build_card(Note(), run(), ctx()))["value"] == OPUS


def test_t2470_a_pin_wins_and_the_chip_shows_its_label() -> None:
    card = build_card(Note(), run(extra={modelpick.PIN: SONNET, "last_model": "opus"}), ctx())
    assert (_picker(card)["value"], card["model"]) == (SONNET, "Sonnet 5.5")


def test_t2471_card_turns_default_to_opus_at_high_effort() -> None:
    card_roles = [r for r in claude.ROLE_MODELS if r != "classify"]
    assert {claude.ROLE_MODELS[r] for r in card_roles} == {"opus"}
    assert {claude.ROLE_EFFORT[r] for r in card_roles} == {"high"}
    assert (claude.ROLE_MODELS["classify"], claude.ROLE_EFFORT["classify"]) == ("haiku", "low")


def test_t2475_every_role_has_a_caller_so_none_hides_from_a_live_check() -> None:
    # `verify` had no caller since the reviewer loop went (no review stage), so C19 could never see it run
    roles = {"spec", "plan", "manager", "closing", "implement", "live_check", "classify"}
    assert set(claude.ROLE_MODELS) == roles
