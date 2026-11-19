"""Closing runs on the board: no Close click (T2060), check-gated restarts, the auto note."""

from dataclasses import replace

from board_helpers import LIMITED, NOW, Note, ctx, run
from contract_lib import validate
from todoimpl.board.actions import ABANDONED, NO_NOTES, actions, check_block
from todoimpl.board.board import build_board
from todoimpl.board.card import build_card
from todoimpl.board.state import RunState
from todoimpl.board.status import Column, Status, column, compute
from todoimpl.board.types import Limit

AUTO = {"reason": "done_check", "passed_at": NOW - 60}
GREEN = {
    "at": NOW,
    "passed": True,
    "trusted": True,
    "reason": "passes, a run already exists",
    "pending": False,
}
RED = {"at": NOW, "passed": False, "trusted": True, "reason": "waiting for a pass", "pending": False}


def closing(**fields: object) -> RunState:
    return run(auto_start=AUTO, **fields)


def ids(
    status: Status, st: RunState, check: dict[str, object] | None = None, limit: Limit | None = None
) -> list[tuple[str, bool]]:
    found = actions(Note(), st, status, limit or Limit(), now=NOW, check=check)
    return [(a.id, a.enabled) for a in found]


def test_t2060_a_closing_run_is_never_ready_to_close_and_closed_is_done() -> None:
    gate = closing(stage="gate")
    assert compute(Note(), gate, live=False, limit_until=None) == Status.SHIPPING
    assert column(Status.SHIPPING) == Column.RUNNING
    assert compute(Note(), closing(stage="closed"), live=False, limit_until=None) == Status.DONE
    assert "ready" not in {c.value for c in Column}


def test_send_is_refused_on_every_closing_run_with_the_fixed_reason() -> None:
    st = closing(stage="failed", error="red", session_id="s1")
    found = actions(Note(), st, Status.NEEDS_YOU, Limit(), now=NOW, check=GREEN)
    send = next(a for a in found if a.id == "send")
    assert (send.enabled, send.reason) == (False, NO_NOTES)
    resume = next(a for a in found if a.id == "copy-resume")
    assert resume.reason == "closing runs have no worktree"


def test_restart_of_a_closing_run_needs_its_check_passing_now() -> None:
    failed = closing(stage="failed", error="red")
    assert ("start", True) in ids(Status.NEEDS_YOU, failed, GREEN)
    assert ("start", False) in ids(Status.NEEDS_YOU, failed, RED)
    assert ("start", True) in ids(Status.CANCELLED, closing(stage="cancelled"), GREEN)
    assert ("start", False) in ids(Status.CANCELLED, closing(stage="cancelled"), None)
    assert ("start", False) in ids(Status.CANCELLED, closing(stage="cancelled"), GREEN, LIMITED)


def test_check_block_names_what_is_missing() -> None:
    assert check_block(None, None) is None
    assert check_block(run(stage="failed"), RED) is None
    assert str(check_block(closing(stage="failed"), None)).startswith("done_check not polled")
    assert check_block(closing(stage="failed"), RED) == "done_check is not passing: waiting for a pass"
    assert check_block(closing(stage="failed"), GREEN) is None


def test_t904_restart_of_a_closing_run_on_an_abandoned_note_says_the_poll_skips_it() -> None:
    st = closing(stage="cancelled")
    found = actions(Note(status="abandoned"), st, Status.CANCELLED, Limit(), now=NOW, check=None)
    start = next(a for a in found if a.id == "start")
    assert (start.enabled, start.reason) == (False, ABANDONED)
    assert ABANDONED == "the note is abandoned: auto close no longer polls its done_check"


def test_card_carries_the_auto_start_badge_and_the_auto_note_only_on_backlog_cards() -> None:
    on = replace(ctx(), auto_close=True, checks={"c59d2588-0": RED})
    card = build_card(Note(), None, on)
    validate("common", card, "task_card")
    assert (card["auto"], card["auto_start"]) == ("waiting for a pass", None)
    assert build_card(Note(), None, replace(on, auto_close=False))["auto"] is None
    done = build_card(Note(), closing(stage="closed"), on)
    validate("common", done, "task_card")
    assert (done["status"], done["auto"], done["auto_start"]) == ("done", None, AUTO)


def test_board_header_says_whether_auto_close_is_on() -> None:
    assert build_board([Note()], {}, ctx(), "b1")["auto_close"] is False
    board = build_board([Note()], {}, replace(ctx(), auto_close=True), "b1")
    validate("board", board)
    assert board["auto_close"] is True
