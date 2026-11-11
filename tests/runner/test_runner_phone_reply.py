"""kuhy's reply to a live check's ask moves the run on: the same ask never comes back to him (T1981)."""

from runnerfakes import Env
from schedfakes import CARD, IMPL, PLAN, boot, reply, wait_stage

PHONE_ASK = reply(
    "- [~] C1: needs phone: the alarm was not seen on the Pixel\n\n"
    "A: phone: with the app on the Pixel, fire a check-in alarm and confirm the shade"
)
HANDS_ASK = reply("- [~] C1: needs phone: not seen\n\nA: check the Home shot on the Pixel and tell me")


def test_t1981_a_reply_to_a_phone_ask_settles_the_checklist_instead_of_asking_again(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, PHONE_ASK, PHONE_ASK, done_check="true")
    try:
        sched.start(CARD)
        rested = wait_stage(world, sched, "live_check", tag="A")
        assert rested.extra.get("waiting_phone")
        sched.send(CARD, "it is ok, push")
        st = wait_stage(world, sched, "gate")
        assert "waiting_phone" not in st.extra
        assert st.extra["partial"]["deferred"] == ["C1"]
        assert len(world.calls()) == 4
    finally:
        sched.close()


def test_t1981_a_reply_to_any_live_check_ask_settles_it_too(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, HANDS_ASK, HANDS_ASK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        calls = len(world.calls())
        sched.send(CARD, "no manual checks on my side, only YOUR checks")
        st = wait_stage(world, sched, "gate")
        assert st.extra["partial"]["deferred"] == ["C1"]
        assert len(world.calls()) == calls + 1
    finally:
        sched.close()


def test_t1981_a_reply_outlasts_the_hands_nudge_it_rearms(world: Env) -> None:
    tap = reply("- [~] C1: needs phone: no taps\n\nA: please tap the toggle on the Pixel")
    sched, _ = boot(world, PLAN, IMPL, tap, tap, tap, tap, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        sched.send(CARD, "it is ok, push")
        st = wait_stage(world, sched, "gate")
        assert st.extra["partial"]["deferred"] == ["C1"]
        assert "reply_carry" not in st.extra
        assert len(world.calls()) == 6
    finally:
        sched.close()
