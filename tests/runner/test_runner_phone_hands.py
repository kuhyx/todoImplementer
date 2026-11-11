"""A live check that asks kuhy for phone hands-on work gets one runner nudge, then rests with the ask."""

from phonefakes import SERIAL, fake_adb, phone_turn
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait, wait_stage
from todoimpl.board.needs import needs
from todoimpl.runner import phone
from todoimpl.runner.phone_sched import PhoneWatcher
from todoimpl.runner.pipeline import NUDGE
from todoimpl.runner.scheduler import COUNTERS

TAP = "A: please tap the toggle on the Pixel and tell me what you see"


def test_t1826_hands_asks_are_told_apart_from_other_asks() -> None:
    for ask in (
        "tap the toggle",
        "open Settings on the phone",
        "look at the real screen",
        "plug in the cable",
        "unplug it",
        "pause your music",
        "look at the phone",
        "feel the vibration",
    ):
        assert phone.asks_for_hands(f"done\n\nA: {ask}"), ask
    for ask in ("which branch should I use?", "merge and deploy first", "stapler is broken"):
        assert not phone.asks_for_hands(f"A: {ask}"), ask
    assert not phone.asks_for_hands("tap it\n\nD: done")
    assert not phone.asks_for_hands("no tag line, tap it")
    assert not phone.asks_for_hands("Q: tap it?")


def test_t1827_a_live_check_that_asks_for_taps_is_nudged_once_and_then_passes(world: Env) -> None:
    sched, _ = boot(world, PLAN, IMPL, reply(f"- [ ] C1: could not tap\n\n{TAP}"), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "gate")
        prompts = [call["prompt"] for call in world.calls()]
        assert len(prompts) == 4
        assert "do not ask kuhy" in prompts[3]
        assert "phone_slot.sh acquire" in prompts[3]
        assert NUDGE not in prompts[3]
        assert not any("do not ask kuhy" in p for p in prompts[:3])
        assert "hands_nudged" not in state(world).extra
        assert "nudge" not in state(world).extra
    finally:
        sched.close()


def test_t1828_a_second_ask_rests_as_needs_you_with_the_ask_text(world: Env) -> None:
    again = reply("- [ ] C1: still no\n\nA: I still need you to tap the toggle on the Pixel")
    sched, _ = boot(world, PLAN, IMPL, reply(f"- [ ] C1: no\n\n{TAP}"), again, done_check="true")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "live_check", tag="A")
        assert len(world.calls()) == 4
        got = needs(st)
        assert got.kind == "claude_action"
        assert got.text == "I still need you to tap the toggle on the Pixel"
        assert st.extra["hands_nudged"] is True
    finally:
        sched.close()


def test_t1829_a_staged_unattached_phone_wait_is_not_nudged(world: Env) -> None:
    fake_adb(world)
    sched, _ = boot(
        world, PLAN, IMPL, phone_turn(world, tag="A: phone: plug in the Pixel"), done_check="true"
    )
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "live_check", tag="A")
        assert len(world.calls()) == 3
        assert needs(st).kind == "phone"
        assert "hands_nudged" not in st.extra
    finally:
        sched.close()


def attached_run(world: Env, last: str) -> None:
    """Drive a staged run until the Pixel shows and its attached turn replied `last`."""
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(world, PLAN, IMPL, phone_turn(world), reply(last), LIVE_OK, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        assert PhoneWatcher(sched).tick() is True
        wait_stage(world, sched, "gate")
    finally:
        sched.close()


def test_t1830_an_attached_turn_asking_for_hands_is_nudged_on_the_same_attached_prompt(world: Env) -> None:
    attached_run(world, "C1: needs a tap\n\nA: phone: tap the toggle on the Pixel for me")
    prompts = [call["prompt"] for call in world.calls()]
    assert len(prompts) == 5
    assert "The Pixel is attached now" in prompts[4]
    assert "do not ask kuhy" in prompts[4]
    assert "do not ask kuhy" not in prompts[3]


def test_t1831_a_lost_phone_ask_on_an_attached_turn_is_not_nudged(world: Env) -> None:
    fake_adb(world, f"{SERIAL} device")
    sched, _ = boot(
        world,
        PLAN,
        IMPL,
        phone_turn(world),
        reply("A: phone: the Pixel is gone, plug it in"),
        done_check="true",
    )
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        assert PhoneWatcher(sched).tick() is True
        st = wait_stage(world, sched, "live_check", tag="A")
        assert len(world.calls()) == 4
        assert needs(st).text == "the Pixel is gone, plug it in"
    finally:
        sched.close()


def test_t1832_a_note_from_kuhy_gives_the_next_ask_a_fresh_nudge(world: Env) -> None:
    assert "hands_nudged" in COUNTERS
    ask = reply(f"- [ ] C1: no\n\n{TAP}")
    sched, _ = boot(world, PLAN, IMPL, ask, ask, ask, ask, done_check="true")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "live_check", tag="A")
        assert state(world).extra["hands_nudged"] is True
        sched.send(CARD, "try again")
        wait_until_calls(world, 6)
        assert "do not ask kuhy" in world.calls()[5]["prompt"]  # T1981 settles only an ask that comes back
    finally:
        sched.close()


def wait_until_calls(world: Env, count: int) -> None:
    """Poll until the fake claude was started `count` times."""
    wait(lambda: len(world.calls()) >= count)
