"""T2006: an `A:` asking for something Claude can run itself is answered by the runner, bounded."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from contract_lib import validate
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait_stage
from todoimpl.board.needs import needs
from todoimpl.board.state import RunState
from todoimpl.runner import grant, scheduler
from todoimpl.umbrella import run as umbrella_run

TUNEDECK = (
    "Run `deploy-todoimpl` (it pulls in 2ab2e5c and restarts the board), then rerun this card's checks; "
    "they should go green with no tunedeck change."
)
YOURSELF = [
    TUNEDECK,
    "Restart the board so the new code is live, then rerun the checks",
    "sudo pacman -S shellcheck, then rerun `make fast`",
    "Push the tag v1.2.0 and run scripts/release.sh",
    "Write the file ~/.config/demo/settings.json with the key set, then run the checks again",
]
KUHY_ONLY = [
    "Which of the two layouts do you want for the header?",
    "Plug in the Pixel: the app passed on the emulator",
    "phone: the install is staged",
    "Is the audio too loud? Listen to the beep",
    "Tap Allow on the phone, then say when it is done",
    "Click Ship on the card when the screenshot looks right",
    "Look at the screen and tell me whether the button is visible",
    "Add your GitHub token to the repo secrets, then rerun the checks",
    "",
]
BLOCK = "A: pick one\n\n```ask\nchoice c1: Layout | wide | *narrow | risk=reversible\n```"


@pytest.mark.parametrize("ask", YOURSELF)
def test_t2006_asks_for_something_claude_can_run_are_answered(ask: str) -> None:
    assert grant.is_autonomous_ask(ask, f"A: {ask}")


@pytest.mark.parametrize("ask", KUHY_ONLY)
def test_t2006_asks_only_kuhy_can_answer_are_not(ask: str) -> None:
    assert not grant.is_autonomous_ask(ask, f"A: {ask}")


def test_t2006_an_ask_block_with_a_choice_or_screenshot_is_kuhys() -> None:
    assert not grant.is_autonomous_ask("Run the thing", BLOCK)
    shot = "A: look\n\n```ask\nscreenshot s1: header | shots/h.png\n```"
    assert not grant.is_autonomous_ask("Run the thing", shot)
    cmd = "A: run it\n\n```ask\ncommand k1: make fast\n```"
    assert grant.is_autonomous_ask("Run the thing", cmd)


def _driver(ask: str, **extra: Any) -> tuple[Any, list[int]]:
    saved: list[int] = []
    st = RunState(task_id="x-0", stage="implement", last_tag="A", extra={"last_reply": f"A: {ask}", **extra})
    return SimpleNamespace(state=st, activity=lambda _t: None, save=lambda: saved.append(1)), saved


def _res(tag: str = "A") -> Any:
    return SimpleNamespace(tag=tag, is_error=False, denials=[])


def test_t2006_a_reply_is_saved_before_the_turn_that_carries_it_starts() -> None:
    driver, saved = _driver(TUNEDECK)
    assert grant.auto_grant(driver, _res(), "implement")
    assert saved == [1]  # a restart during the granted turn must not grant the same ask again
    assert driver.state.extra[grant.RUN_KEY] == 1
    assert driver.state.extra["granted_note"].startswith("(runner) Granted:")


def test_t2006_a_spent_run_budget_parks_the_ask_whatever_the_stage() -> None:
    driver, saved = _driver(TUNEDECK, **{grant.RUN_KEY: grant.MAX_GRANTS_RUN})
    assert not grant.auto_grant(driver, _res(), "live_check")
    assert saved == []
    assert "granted_note" not in driver.state.extra


def test_t2006_a_refused_tool_call_is_not_answered_with_words() -> None:
    driver, saved = _driver(TUNEDECK)
    res = _res()
    res.denials = [object()]
    assert not grant.auto_grant(driver, res, "implement")
    assert saved == []


def test_t2006_an_umbrella_child_keeps_its_own_bounce_for_asks_that_are_not_permission() -> None:
    driver, _ = _driver(TUNEDECK, umbrella_round=1)
    assert not grant.auto_grant(driver, _res(), "implement")
    permission, _ = _driver("OK me to push, then run install.sh", umbrella_round=1)
    assert grant.auto_grant(permission, _res(), "implement")


def test_t2006_the_budget_survives_a_turn_that_ends_on_r() -> None:
    driver, _ = _driver(TUNEDECK, **{grant.RUN_KEY: 1, "ask_grants": {"implement": 1}})
    assert not grant.auto_grant(driver, _res("R"), "implement")
    assert driver.state.extra[grant.RUN_KEY] == 1  # only the per-stage count resets
    assert "ask_grants" not in driver.state.extra


def test_t2006_the_tunedeck_ask_resumes_the_session_and_the_card_goes_on(world: Env) -> None:
    ask = reply(f"Checks need the new board.\n\nA: {TUNEDECK}")
    sched, _ = boot(world, PLAN, ask, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        calls = world.calls()
        assert calls[2]["resume"] is not None
        assert "(runner) Granted:" in calls[2]["prompt"]
        assert "do it yourself" in calls[2]["prompt"].lower()
        assert st.extra[grant.RUN_KEY] == 1
        validate("state", st.to_dict())
        assert "never in ~/src/<repo>" in calls[2]["prompt"]
    finally:
        sched.close()


def test_t2006_after_the_budget_the_card_rests_on_kuhy_as_before(world: Env) -> None:
    again = reply(f"Still blocked.\n\nA: {TUNEDECK}\n\n```ask\ncommand k1: deploy-todoimpl\n```")
    sched, _ = boot(world, PLAN, reply(f"A: {TUNEDECK}"), again, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        assert len(world.calls()) == 3
        assert needs(st).kind == "claude_action"
        assert state(world).extra[grant.RUN_KEY] == 1
    finally:
        sched.close()


def test_t2006_start_retry_and_a_note_clear_the_run_budget(world: Env) -> None:
    sched, _ = boot(world)
    try:
        st = RunState(task_id=CARD, stage="gate", extra={grant.RUN_KEY: 2, "ask_grants": {"implement": 1}})
        sched._route(st)  # what a note from kuhy does to a run
        assert grant.RUN_KEY not in st.extra
    finally:
        sched.close()
    assert grant.RUN_KEY in scheduler.COUNTERS
    assert grant.RUN_KEY in umbrella_run.COUNTERS
