from board_helpers import Note, run
from todoimpl.board.status import Status, compute, needs

WAIT = {"apk": "/a.apk", "criteria": ["C1"]}


def test_t1540_a_phone_wait_is_its_own_needs_kind_ahead_of_every_other_reason() -> None:
    for fields in (
        {},
        {"assignee": "human"},
        {"stage": "spec_wait"},
        {"stage": "live_check"},
    ):
        state = run(last_tag="A", extra={"waiting_phone": WAIT}, **fields)
        got = needs(state)
        assert got.kind == "phone"
        assert "Pixel" in got.text


def test_t1541_a_phone_wait_is_needs_you_until_the_phone_requeues_it() -> None:
    waiting = run(last_tag="A", extra={"waiting_phone": WAIT})
    assert compute(Note(), waiting, live=False, limit_until=None) == Status.NEEDS_YOU
    requeued = run(last_tag=None, stage="live_check", extra={"waiting_phone": WAIT, "phone_attached": True})
    assert compute(Note(), requeued, live=False, limit_until=None) == Status.QUEUED


def test_a_phone_wait_never_hides_an_error_or_a_question() -> None:
    assert needs(run(last_tag="A", error="boom", extra={"waiting_phone": WAIT})).kind == "claude_action"
    assert needs(run(last_tag="Q", extra={"waiting_phone": WAIT})).kind == "claude_question"
