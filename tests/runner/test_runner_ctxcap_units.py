"""The context cap's pieces: the meter, the cap setting, the brake, the marker, the seed."""

import json
from typing import Any

import pytest
from todoimpl.board.state import RunState
from todoimpl.runner import ctxcap
from todoimpl.runner.stream import StreamParser, TurnResult


def event(usage: object, *, parent: object = None, message: object = "default") -> dict[str, Any]:
    body = {"id": "m", "usage": usage} if message == "default" else message
    return {"type": "assistant", "message": body, "parent_tool_use_id": parent}


def run() -> RunState:
    return RunState(task_id="abcd1234-0", stage="implement")


def test_t2368_the_cap_is_150000_by_default_zero_is_off_and_junk_falls_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ctxcap.ENV, raising=False)
    assert ctxcap.cap() == 150_000
    for text, want in (("0", 0), ("123456", 123_456), ("", 150_000), ("lots", 150_000), ("-5", 150_000)):
        monkeypatch.setenv(ctxcap.ENV, text)
        assert ctxcap.cap() == want


def test_t2365_the_meter_adds_the_three_input_kinds_of_the_main_thread_only() -> None:
    usage = {
        "input_tokens": 3,
        "cache_creation_input_tokens": 40,
        "cache_read_input_tokens": 500,
        "output_tokens": 9,
    }
    assert ctxcap.context_of(event(usage)) == 543  # output is not context
    assert ctxcap.context_of(event(usage, parent="toolu_1")) is None  # a subagent's message
    assert ctxcap.context_of(event(None)) is None
    assert ctxcap.context_of(event(None, message=None)) is None
    assert ctxcap.context_of(event({"input_tokens": 0})) is None  # a synthetic message
    assert ctxcap.context_of(event({"input_tokens": True, "cache_read_input_tokens": "9"})) is None


def test_t2365_the_parser_keeps_the_latest_main_thread_context_and_tells_the_brake() -> None:
    parser, told = StreamParser(), list[int]()
    parser.on_context = told.append
    for tokens, parent in ((100, None), (900, "toolu_1"), (250, None)):
        parser.feed(json.dumps(event({"input_tokens": tokens}, parent=parent)))
    assert told == [100, 250]
    assert parser.result.context_tokens == 250  # the latest, so a shrunk context counts as shrunk
    quiet = StreamParser()
    quiet.feed(json.dumps(event({"input_tokens": 7})))  # nobody listens (a killed turn read again)
    assert quiet.result.context_tokens == 7
    assert ctxcap.size(quiet.result) == {"context_tokens": 7, "calls": 1}
    assert ctxcap.size(TurnResult()) == {}


def test_t2363_the_brake_stops_once_at_exactly_the_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ctxcap.ENV, "1000")
    st, stops = run(), list[str]()
    on_context = ctxcap.brake(st, "implement", lambda: stops.append("stop"))
    assert on_context is not None
    on_context(999)
    assert stops == []
    on_context(1000)  # at the cap, not above it
    on_context(1500)
    assert stops == ["stop"]
    assert st.extra[ctxcap.HIT] == {"role": "implement", "tokens": 1000, "cap": 1000}


def test_t2368_no_brake_with_the_cap_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ctxcap.ENV, "0")
    monkeypatch.setenv(ctxcap.CALL_ENV, "0")
    assert ctxcap.brake(run(), "implement", lambda: None) is None


def test_t2369_a_role_cut_eight_times_without_a_finished_turn_is_left_alone(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(ctxcap.ENV, raising=False)
    st = run()
    st.extra[ctxcap.FRESH] = {"implement": {"tokens": 1, "cap": 1, "streak": ctxcap.MAX_STREAK - 1}}
    assert ctxcap.brake(st, "implement", lambda: None) is not None
    st.extra[ctxcap.FRESH]["implement"]["streak"] = ctxcap.MAX_STREAK
    assert ctxcap.brake(st, "implement", lambda: None) is None  # the loop guard: no endless fresh sessions
    assert ctxcap.brake(st, "plan", lambda: None) is not None  # another role is not held back


def test_t2367_a_cut_counts_a_reseed_and_a_finished_turn_ends_the_seed() -> None:
    st = run()
    st.extra[ctxcap.HIT] = {"role": "implement", "tokens": 310_000, "cap": 300_000}
    assert ctxcap.mark(st, "implement", TurnResult()) is True
    assert st.extra[ctxcap.RESEEDS] == {"implement": 1}
    assert "310000 of 300000 tokens" in ctxcap.seed(st, "implement").replace(",", "")
    assert ctxcap.seed(st, "plan") == ""
    st.extra[ctxcap.HIT] = {"role": "implement", "tokens": 320_000, "cap": 300_000}  # cut again, still fresh
    assert ctxcap.mark(st, "implement", TurnResult()) is True
    assert st.extra[ctxcap.RESEEDS] == {"implement": 2}
    assert st.extra[ctxcap.FRESH]["implement"]["streak"] == 2
    assert (
        ctxcap.mark(st, "implement", TurnResult()) is False
    )  # an unfinished turn that was not cut: still fresh
    assert ctxcap.seed(st, "implement")
    assert ctxcap.mark(st, "plan", TurnResult(finished=True)) is False  # another role's end changes nothing
    assert ctxcap.seed(st, "implement")
    assert ctxcap.mark(st, "implement", TurnResult(finished=True)) is False
    assert ctxcap.FRESH not in st.extra
    assert st.extra[ctxcap.RESEEDS] == {"implement": 2}  # the count stays


def test_t2363_a_turn_cut_on_its_last_event_that_still_finished_goes_on_and_the_next_is_fresh() -> None:
    st = run()
    st.extra[ctxcap.HIT] = {"role": "implement", "tokens": 301_000, "cap": 300_000}
    st.extra[ctxcap.FRESH] = {"implement": {"tokens": 1, "cap": 1, "streak": 5}}
    assert (
        ctxcap.mark(st, "implement", TurnResult(finished=True)) is False
    )  # its result came: nothing to rerun
    assert st.extra[ctxcap.FRESH]["implement"]["streak"] == 1  # it finished: the streak starts over
    assert ctxcap.seed(st, "implement")


def test_t2363_a_stop_of_another_roles_turn_is_not_this_roles() -> None:
    st = run()
    st.extra[ctxcap.HIT] = {"role": "live_check", "tokens": 400_000, "cap": 300_000}
    assert ctxcap.mark(st, "implement", TurnResult()) is False
    assert ctxcap.HIT not in st.extra
    assert ctxcap.RESEEDS not in st.extra


def test_t2366_go_on_resumes_after_the_credit_cap_and_restarts_fresh_after_the_context_cap() -> None:
    st = run()
    assert ctxcap.go_on(st, TurnResult(), cut=False) is False
    st.extra["cap_hit"] = True
    assert ctxcap.go_on(st, TurnResult(finished=True), cut=False) is False  # it finished: nothing to redo
    assert "cap_hit" not in st.extra
    st.extra["cap_hit"] = True
    assert ctxcap.go_on(st, TurnResult(), cut=False) is True
    assert st.extra["r_continue"] is True  # the credit cap: the same session goes on at the plan
    st.extra.clear()
    assert ctxcap.go_on(st, TurnResult(), cut=True) is True
    assert "r_continue" not in st.extra  # the context cap: no continue prompt, a fresh session instead
