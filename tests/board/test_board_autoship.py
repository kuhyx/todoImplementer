"""The Auto-ship option rides on Start/Restart only, disabled with a reason without a done_check."""

from typing import Any

from board_helpers import NOW, Note, run
from contract_lib import validate
from todoimpl.board.actions import Action, actions
from todoimpl.board.status import Status
from todoimpl.board.types import Limit


def _start(status: Status, note: Note, **fields: Any) -> Action:
    state = None if status == Status.BACKLOG else run(**{"stage": "cancelled", **fields})
    got = {a.id: a for a in actions(note, state, status, Limit(), now=NOW)}
    return got["start"]


def test_start_on_a_done_check_note_offers_auto_ship_unticked() -> None:
    start = _start(Status.BACKLOG, Note())
    assert start.option is not None
    assert (start.option.id, start.option.label, start.option.enabled) == (
        "auto_ship",
        "Auto-ship when checks pass",
        True,
    )
    out = start.to_dict()
    validate("common", out, "action")
    assert out["option"] == {
        "id": "auto_ship",
        "label": "Auto-ship when checks pass",
        "enabled": True,
        "reason": None,
    }


def test_auto_ship_is_disabled_with_a_reason_without_a_done_check() -> None:
    start = _start(Status.BACKLOG, Note(done_check=None))
    assert start.enabled
    assert start.option is not None
    assert (start.option.enabled, start.option.reason) == (False, "the note has no done_check")
    validate("common", start.to_dict(), "action")


def test_restart_offers_auto_ship_but_retry_and_hand_back_do_not() -> None:
    assert _start(Status.CANCELLED, Note()).option is not None
    retry = _start(Status.NEEDS_YOU, Note(), stage="failed", error="push refused")
    assert retry.label == "Retry"
    assert retry.option is None
    assert "option" not in retry.to_dict()
