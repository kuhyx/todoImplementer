"""T2048: an `A:` with no ask block is sent back once, so the card shows buttons or an exact step."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, wait_stage
from todoimpl.asks.parse import parse_asks
from todoimpl.board.state import RunState
from todoimpl.prompts.standing import GRANT
from todoimpl.runner import askform

DECIDE = "decide whether TUTOR gets a Caddy block behind the phone gate, and whether to restart the card."
VAGUE = "C7 still needs a track that is not prefetched. Alternatively, kuhy can confirm the flow himself."
BLOCK = "A: pick\n\n```ask\nchoice c1: Caddy block | yes | *no | risk=reversible\n```"


def _driver(text: str, **extra: Any) -> tuple[Any, list[int]]:
    saved: list[int] = []
    st = RunState(task_id="x-0", stage="live_check", last_tag="A", extra={"last_reply": text, **extra})
    return SimpleNamespace(state=st, activity=lambda _t: None, save=lambda: saved.append(1)), saved


def _res(tag: str = "A") -> Any:
    return SimpleNamespace(tag=tag, is_error=False, denials=[])


@pytest.mark.parametrize("ask", [DECIDE, VAGUE])
def test_t2048_a_bare_a_is_sent_back_for_an_ask_block(ask: str) -> None:
    driver, saved = _driver(f"Done.\n\nA: {ask}")
    assert askform.needs_form(driver, _res(), "live_check")
    note = driver.state.extra["granted_note"]
    assert saved == [1]
    assert "```ask" in note
    assert "choice <id>:" in note
    assert "command <id>:" in note


def test_t2048_the_note_hands_every_phone_and_device_check_back_to_claude() -> None:
    driver, _ = _driver(f"A: {VAGUE}")
    askform.needs_form(driver, _res(), "live_check")
    note = driver.state.extra["granted_note"]
    assert "phone, device" in note
    assert "yourself" in note


def test_t2048_a_reply_with_an_ask_block_is_left_alone() -> None:
    driver, saved = _driver(BLOCK)
    assert not askform.needs_form(driver, _res(), "live_check")
    assert saved == []


@pytest.mark.parametrize("stage", ["spec", "plan"])
def test_t2048_stages_that_edit_nothing_are_left_alone(stage: str) -> None:
    driver, _ = _driver(f"A: {DECIDE}")
    assert not askform.needs_form(driver, _res(), stage)


def test_t2048_a_phone_wait_an_error_and_an_unattended_run_are_left_alone() -> None:
    waiting, _ = _driver(f"A: {DECIDE}", waiting_phone={"criteria": ["C7"]})
    assert not askform.needs_form(waiting, _res(), "live_check")
    child, _ = _driver(f"A: {DECIDE}", umbrella_round=1)
    assert not askform.needs_form(child, _res(), "live_check")
    broken = _res()
    broken.is_error = True
    driver, _ = _driver(f"A: {DECIDE}")
    assert not askform.needs_form(driver, broken, "live_check")


def test_t2048_a_tap_ask_keeps_its_own_phone_nudge() -> None:
    driver, saved = _driver("- [ ] C1: no\n\nA: I need you to tap the toggle on the Pixel")
    assert not askform.needs_form(driver, _res(), "live_check")
    assert saved == []


def test_t2048_a_turn_that_ends_on_anything_but_a_resets_the_stage_count() -> None:
    driver, _ = _driver("R: going on", ask_forms={"live_check": 1})
    assert not askform.needs_form(driver, _res("R"), "live_check")
    assert "ask_forms" not in driver.state.extra


def test_t2048_one_send_back_per_stage_and_two_per_run() -> None:
    again, _ = _driver(f"A: {DECIDE}", ask_forms={"live_check": 1})
    assert not askform.needs_form(again, _res(), "live_check")
    spent, _ = _driver(f"A: {DECIDE}", **{askform.RUN_KEY: askform.MAX_FORMS_RUN})
    assert not askform.needs_form(spent, _res(), "implement")


def test_t2048_the_standing_prompt_gives_phone_checks_to_claude_not_kuhy() -> None:
    assert "(phone, audio, screen)" not in GRANT
    assert "Phone, device" in GRANT
    assert "yourself" in GRANT


def test_t2048_the_session_answers_with_a_block_and_the_card_gets_buttons(world: Env) -> None:
    bare = reply(f"Checked.\n\nA: {DECIDE}")
    fixed = reply(f"A: {DECIDE}\n\n```ask\nchoice c1: Caddy block | yes | *no | risk=reversible\n```")
    sched, _ = boot(world, PLAN, bare, fixed, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "implement", tag="A")
        calls = world.calls()
        assert calls[2]["resume"] is not None
        assert "(runner) Your `A:`" in calls[2]["prompt"]
        assert [a.id for a in parse_asks(str(st.extra["last_reply"]))] == ["c1"]
    finally:
        sched.close()
