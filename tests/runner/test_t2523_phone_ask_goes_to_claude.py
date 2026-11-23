"""T2523: a phone-only ask past its two send-backs goes to a Claude turn, never to kuhy (card c96b7ce5).

T2522 sent an ask of phone work only back to its session twice per run; the third one still rested in
Needs you. Now the card goes on to a fresh live check (from implement) or a fix turn (from the live check),
both carrying the phone note, and the usual live-check rules settle it.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from runnerfakes import Env
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, reply, state, wait
from todoimpl.runner import devicework

ASK = "```ask\nchoice c1: Rate a few reviews on the phone | *approve | change\n```\n\nA: rate them"
LIVE_ASK = reply(f"- [ ] C1: needs reviews rated on the phone\n\n{ASK}")
IMPL_ASK = reply(f"C1: not done - needs the phone\n\n{ASK}")


def _rested(world: Env, sched: Any) -> bool:
    st = state(world)
    rest = st.stage in ("gate", "failed") or (st.stage in ("implement", "live_check") and st.last_tag == "A")
    return rest and CARD not in sched.running()


def _drive(world: Env, *turns: tuple[dict[str, Any], ...]) -> tuple[Any, list[str]]:
    sched, _ = boot(world, PLAN, *turns, done_check="true")
    try:
        sched.start(CARD)
        wait(lambda: _rested(world, sched), 20.0 * len(turns))
        return state(world), [str(call["prompt"]) for call in world.calls()]
    finally:
        sched.close()


def test_t2523_a_third_phone_ask_in_the_live_check_goes_to_a_fix_turn(world: Env) -> None:
    st, prompts = _drive(world, IMPL, LIVE_ASK, LIVE_ASK, LIVE_ASK, IMPL, LIVE_OK)
    assert st.stage == "gate", (st.stage, st.error)
    assert len(prompts) == 7
    assert "phone_vd.sh" in prompts[5]  # the fix turn carries the phone note


def test_t2523_a_third_phone_ask_in_implement_goes_to_a_fresh_live_check(world: Env) -> None:
    st, prompts = _drive(world, IMPL_ASK, IMPL_ASK, IMPL_ASK, LIVE_OK)
    assert st.stage == "gate", (st.stage, st.error)
    assert len(prompts) == 5
    assert "phone_vd.sh" in prompts[4]


@pytest.mark.parametrize(
    ("tag", "reply_text", "extra"),
    [
        ("Q", ASK, {}),
        ("A", "```ask\nchoice c1: Caddy block | yes | *no\n```\n\nA: pick", {}),
        ("A", ASK, {"umbrella_round": 1}),
        ("A", ASK, {"waiting_phone": {"note": "plug"}}),
    ],
)
def test_t2523_other_rests_stay_where_they_are(tag: str, reply_text: str, extra: dict[str, Any]) -> None:
    st = SimpleNamespace(extra={"last_reply": reply_text, **extra}, task_id="t")
    driver: Any = SimpleNamespace(state=st, activity=lambda _t: None)
    res: Any = SimpleNamespace(tag=tag)
    assert not devicework.to_claude(driver, res)
    assert "nudge" not in st.extra
