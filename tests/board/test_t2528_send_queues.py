"""T2528: Send to Claude is enabled on every open card but a closing one; the note waits for the next turn."""

from __future__ import annotations

import pytest
from board_helpers import LIMITED, NOW, Note, run
from todoimpl.board.actions import NO_NOTES, actions
from todoimpl.board.state import RunState
from todoimpl.board.status import Status
from todoimpl.board.types import Limit

S = Status


def _send(status: Status, state: RunState, *, limited: bool = False) -> tuple[bool, str | None] | None:
    got = {a.id: a for a in actions(Note(), state, status, LIMITED if limited else Limit(), now=NOW)}
    return (got["send"].enabled, got["send"].reason) if "send" in got else None


@pytest.mark.parametrize(
    ("status", "state", "limited"),
    [
        (S.WORKING, run(), False),  # the first turn runs: no session id yet (the screenshot)
        (S.WORKING, run(session_id="s"), True),
        (S.QUEUED, run(), False),
        (S.QUEUED, run(session_id="s"), True),
        (S.PAUSED_LIMIT, run(stage="paused_limit", session_id="s"), True),
        (S.WORKING, run(stage="paused_retry", session_id="s"), False),
        (S.SHIPPING, run(stage="shipping", session_id="s"), False),
        (S.SHIPPING, run(stage="shipping"), True),
        (S.NEEDS_YOU, run(stage="failed", error="boom", session_id="s"), True),
    ],
)
def test_t2528_send_is_enabled_on_every_open_card(status: Status, state: RunState, limited: bool) -> None:
    assert _send(status, state, limited=limited) == (True, None)


def test_t2528_closing_and_done_cards_take_no_notes() -> None:
    assert _send(
        S.WORKING, run(stage="checks", auto_start={"reason": "done_check", "passed_at": 1.0}, session_id="s")
    ) == (False, NO_NOTES)
    assert _send(S.DONE, run(stage="shipped", session_id="s")) is None
