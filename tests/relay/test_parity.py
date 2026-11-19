"""Guard 4: a relay request gets what the same click over HTTP gets, from one Router and backend."""

from typing import Any

import pytest
from httpfakes import FakeBackend
from relayfakes import Recorder, answer, board_handlers, req
from rtdb_relay.seal import pruned
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.relay import bridge, kinds

GROUP = "0123456789ab"


def bodies(card: str) -> dict[str, dict[str, Any]]:
    """One valid body per routed kind."""
    card_args = {"card": card, "args": {}}
    return {
        "task_start": {"card": card, "args": {"auto_ship": False}},
        "task_spec_answers": {"card": card, "args": {"answers": {"Q1": "yes"}}},
        "task_spec_ok": card_args,
        "task_send": {"card": card, "args": {"text": "go on"}},
        "task_ship": card_args,
        "task_close": card_args,
        "task_cancel": card_args,
        "task_lesson_approve": {"card": card, "args": {"lesson_id": "L1"}},
        "task_go": card_args,
        "task_rerun": card_args,
        "task_wont": card_args,
        "task_done_manually": card_args,
        "task_model": {"card": card, "args": {"model": "claude-fable-5-2"}},
        "ask_answer": {"card": card, "args": {"ask": "pick", "option": "a"}},
        "ask_take_recommended": card_args,
        "ask_run": {"card": card, "args": {"ask": "cmd", "add": True}},
        "ask_undo": {"card": card, "args": {"ask": "pick"}},
        "ask_approve": {"card": card, "args": {"ask": "shot"}},
        "ask_reject": {"card": card, "args": {"ask": "shot"}},
        "new_task": {"args": {"text": "x"}},  # refused by the route the same way on both sides
        "credits_fallback": {"args": {"enabled": True}},
        "merge_merge": {"group": GROUP, "args": {}},
        "merge_dismiss": {"group": GROUP, "args": {}},
        "session_resume": {"args": {}},
        "session_mark": {"args": {}},
        "session_delete": {"args": {}},
        "session_handoff": {"args": {}},
        "task_detail": {"card": card},
        "task_issues": {"card": card},
        "task_shot": {"card": card, "name": "shots/a.png"},
        "umbrella": {"card": card},
        "umbrella_log": {"card": card, "log": card},
        "tokens": {"path": "/schema", "query": ""},
    }


def http(router: Router, kind: str, body: dict[str, Any]) -> tuple[str, Any]:
    """Send the same click to the Router directly: ("ok", data) or ("refused", code)."""
    reply = bridge.send(router, kinds.ROUTED[kind].call(body))
    if reply.status != 200:
        return "refused", bridge.refusal(reply).code
    return "ok", pruned(bridge.data_of(reply))  # RTDB keeps no null and no empty list or object


def test_every_routed_kind_has_a_parity_case(backend: FakeBackend) -> None:
    assert set(bodies(backend.task_id)) == set(kinds.ROUTED)


@pytest.mark.parametrize("kind", sorted(kinds.ROUTED))
def test_relay_matches_http(fake: FakeRtdb, router: Router, backend: FakeBackend, kind: str) -> None:
    backend.ask_service = Recorder()  # type: ignore[attr-defined]
    backend.merge_service = Recorder()  # type: ignore[attr-defined]
    backend.shots["shots/a.png"] = b"\x89PNG1"
    body = bodies(backend.task_id)[kind]
    [result] = answer(fake, board_handlers(router), [req(kind, body)])
    calls_relay = list(backend.calls) + list(backend.ask_service.calls)  # type: ignore[attr-defined]
    backend.calls.clear()
    backend.ask_service.calls.clear()  # type: ignore[attr-defined]
    side, value = http(router, kind, body)
    calls_http = list(backend.calls) + list(backend.ask_service.calls)  # type: ignore[attr-defined]
    if side == "ok":
        assert result["ok"] is True
        assert result.get("data") == value  # both None when the body was {} (RTDB drops it)
    else:
        assert (result["ok"], result["code"]) == (False, value)
    assert calls_relay == calls_http
