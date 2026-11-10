from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, state, wait_stage
from todoimpl.board.state import NOTE_BODY_MAX


def test_t1862_start_records_the_note_body_cut_to_the_cap(world: Env) -> None:
    body = "keep me " + "y" * NOTE_BODY_MAX
    sched, _ = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt", body=body)
    try:
        sched.start(CARD)
        assert state(world).note_body == body[:NOTE_BODY_MAX]
        wait_stage(world, sched, "gate")
    finally:
        sched.close()
