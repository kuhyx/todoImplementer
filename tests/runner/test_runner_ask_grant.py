"""T1863: an `A:` that only asks for permission is granted once by the runner, not parked on kuhy."""

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.board.needs import needs
from todoimpl.runner import grant

ASKS = [
    "OK me to commit todo-wt, merge it into ~/src/todo main, push, and run mcp/install.sh",
    "create the confirmation marker... or write the two files by hand. Then press Retry",
    "send a `LONG:` turn to launch the run",
    "after the server commits and tags crdt_sync_dart-v0.11.4, bump ~/src/todo/pubspec.yaml",
    "Tutor half not started: no tutor worktree, and editing main is off-limits",
    "Should I push this now, or do you want to review it first? I need your approval",
    "I may not run the installer without permission",
    "Run ./install.sh yourself, then press Retry",
]
REAL_ASKS = [
    "Which of the two layouts do you want for the header?",
    "Plug in the Pixel: the app passed on the emulator",
    "phone: the install is staged",
    "Is the audio too loud? Listen to the beep",
]


@pytest.mark.parametrize("ask", ASKS)
def test_permission_asks_are_recognised(ask: str) -> None:
    assert grant.is_permission_ask(ask)


@pytest.mark.parametrize("ask", REAL_ASKS)
def test_real_asks_are_not_permission(ask: str) -> None:
    assert not grant.is_permission_ask(ask)


def test_t1863_a_permission_ask_resumes_the_same_session_once(world: Env) -> None:
    ask = reply("Done but not landed.\n\nA: OK me to commit and push, then run install.sh")
    sched, _ = boot(world, PLAN, ask, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert calls[2]["resume"] is not None
        assert "(runner) Granted:" in calls[2]["prompt"]
        assert "(runner) Granted:" not in calls[1]["prompt"]
        assert "(runner) Granted:" not in calls[3]["prompt"]
        texts = [e["text"] for e in sched.bus.history(CARD, 0)]
        assert any("auto-granted" in t and "OK me to commit" in t for t in texts)
        assert "ask_grants" not in st.extra
    finally:
        sched.close()


def test_t1863_a_second_permission_ask_parks_the_card(world: Env) -> None:
    ask = reply("A: OK me to commit and push?")
    again = reply("Still blocked.\n\nA: may I push now?")
    sched, _ = boot(world, PLAN, ask, again, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        assert len(world.calls()) == 3
        assert needs(st).kind == "claude_action"
        assert "may I push now" in needs(st).text
    finally:
        sched.close()


def test_t1863_a_real_ask_is_not_granted(world: Env) -> None:
    ask = reply("A: Which of the two layouts do you want?")
    sched, _ = boot(world, PLAN, ask, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        wait_stage(world, sched, "implement", tag="A")
        assert len(world.calls()) == 2
    finally:
        sched.close()
