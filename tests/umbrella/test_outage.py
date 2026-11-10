"""No internet or no gateway: the round rests with a reason and retries by itself, nothing escalates."""

from __future__ import annotations

import socket

import pytest
from runnerfakes import Env
from schedfakes import wait
from tierfakes import Free
from todoimpl.runner import freegate, netwait
from todoimpl.umbrella import issues
from umbrellarig import CARD, NOTE, at_rest, boot, manager, script_live, umbrella

REAL_PROBE = netwait.probe  # the autouse fixture swaps netwait.probe; the real one is tested below


def _resting(world: Env) -> bool:
    return umbrella(world).stage == "paused_retry"


def test_t1904_no_network_pauses_the_round_before_any_turn_and_resumes_when_it_returns(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    up = {"now": False}
    monkeypatch.setattr(netwait, "probe", lambda: up["now"])
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        wait(lambda: _resting(world))
        st = umbrella(world)
        assert (st.extra["retry_kind"], st.extra["net_retries"]) == ("network", 1)
        assert "offline" in str(st.extra["retry_reason"])
        assert not world.calls()  # no manager turn, no tokens spent
        up["now"] = True
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    assert st.error is None
    assert "net_retries" not in st.extra
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["ok"] is True


def test_t1904_an_unreachable_gateway_pauses_the_round_and_is_logged_once_per_attempt(
    world: Env, free: Free, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([("gateway probe: URLError: refused", True), None])
    monkeypatch.setattr(freegate, "_gateway_error", lambda _key: next(answers))
    sched, _ = boot(world, 1)
    world.script(NOTE, *manager("CHILD kuhyx/alpha: clean"))
    script_live(world, 1)
    try:
        sched.start(CARD)
        wait(lambda: _resting(world))
        st = umbrella(world)
        assert st.extra["retry_kind"] == "gateway"
        assert st.extra["gw_retries"] == 1
        assert not world.calls()
        st = at_rest(world, sched, "gate")
    finally:
        sched.close()
    (row,) = issues.read(world.root / CARD)
    assert row["phase"] == "start"
    assert "refused" in row["symptom"]
    assert row["action"] == "the round waits for the gateway"
    assert st.extra["umbrella"]["rounds"][0]["children"][0]["free"] is True
    assert "gw_retries" not in st.extra


def test_the_probe_connects_to_the_first_host_that_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    asked: list[tuple[str, int]] = []

    class Sock:
        def close(self) -> None:
            asked.append(("closed", 0))

    def connect(host: tuple[str, int], timeout: float) -> Sock:
        asked.append(host)
        if host[0] == "api.anthropic.com":
            raise OSError
        assert timeout == netwait.TIMEOUT <= 2.0
        return Sock()

    monkeypatch.setattr(socket, "create_connection", connect)
    assert REAL_PROBE() is True
    assert asked == [("api.anthropic.com", 443), ("1.1.1.1", 443), ("closed", 0)]


def test_the_probe_says_no_when_nothing_answers(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(_host: tuple[str, int], timeout: float) -> None:
        raise OSError

    monkeypatch.setattr(socket, "create_connection", refuse)
    assert REAL_PROBE() is False
    assert netwait.online() is True  # online() asks the (stubbed) probe
