"""Cancel: a resting run stops at once and its note is abandoned in the todo app where it can be (T1815)."""

from runnerfakes import Env
from schedfakes import CARD, PLAN, boot, reply, state, wait_stage


def test_cancel_of_a_resting_run_is_immediate(world: Env) -> None:
    sched, client = boot(world, PLAN, reply("Q: which?"), done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement")
        sched.cancel(CARD)
        assert state(world).stage == "cancelled"
        assert client.abandoned == [CARD]
    finally:
        sched.close()


def test_t1815_a_todo_app_error_never_blocks_cancel(world: Env) -> None:
    sched, client = boot(world, PLAN, reply("Q: which?"), done_check="true")
    client.fail_abandon = True
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement")
        sched.cancel(CARD)
        assert state(world).stage == "cancelled"
        assert client.abandoned == []
    finally:
        sched.close()
