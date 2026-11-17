# ruff: noqa: FBT003
"""The waiting-for-phone status and the app-error badge of a card: the server decides, the page draws."""

from board_helpers import Note, ctx, run
from contract_lib import validate
from todoimpl.board import board
from todoimpl.board.card import build_card
from todoimpl.board.status import Column, Status, column, compute

WAIT = {"since": 5.0, "tries": 1}


def waiting(**fields: object) -> dict[str, object]:
    return build_card(
        Note(),
        run(stage="failed", error="pushed, not deployed: x", extra={"phone_update": WAIT, **fields}),
        ctx(),
    )


def test_t2023_a_failed_run_that_waits_for_the_phone_has_its_own_status() -> None:
    assert (
        compute(Note(), run(stage="failed", extra={"phone_update": WAIT}), False, None)
        == Status.WAITING_PHONE_UPDATE
    )
    assert compute(Note(), run(stage="failed"), False, None) == Status.NEEDS_YOU
    assert column(Status.WAITING_PHONE_UPDATE) == Column.RUNNING


def test_t2023_the_card_says_what_it_waits_for_and_offers_retry_and_cancel() -> None:
    card = waiting()
    assert card["status"] == "waiting_phone_update"
    assert card["column"] == "running"
    assert card["needs"] is None
    assert card["current"] == "wait for phone to connect, then update the app"
    actions = {a["id"]: a["enabled"] for a in card["actions"]}  # type: ignore[attr-defined]
    assert (actions["start"], actions["cancel"]) == (True, True)  # Retry deploys now; Cancel stops the run
    validate("board", {**board.build_board([Note()], {}, ctx(), "b"), "tasks": [card]})


def test_t2024_a_card_counts_the_error_parts_in_its_text() -> None:
    plain = build_card(Note(), None, ctx())
    assert "app_error" not in plain
    text = (
        "### Part a-1: x\nError-Signature: kartka:1\n\n### Part b-2: y\nnothing\n\n"
        "### Part c-3: z\nError-Signature: kartka:2"
    )
    card = build_card(Note(body=text), None, ctx())
    assert card["app_error"] == 2
    validate("board", {**board.build_board([Note()], {}, ctx(), "b"), "tasks": [card]})
