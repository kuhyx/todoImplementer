"""POST actions over a real socket: CSRF, body checks, enabled-action gate, error mapping."""

import http.client
import json
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import POST_ACTIONS, FakeBackend, Live, call, post
from todoimpl.http.backend import BackendError


@pytest.mark.parametrize("action", POST_ACTIONS)
def test_every_post_action_calls_the_backend_and_returns_the_card(live: Live, action: str) -> None:
    bodies: dict[str, Any] = {
        "spec-answers": {"answers": {"Q1": "yes"}},
        "send": {"text": "hello"},
        "lesson-approve": {"lesson_id": "L1"},
        "model": {"model": "claude-fable-5-2"},
    }
    r = post(live, action, bodies.get(action, {}))
    assert r.status == 200, r.body
    body = r.json()
    validate("response", body)
    assert body["ok"] is True
    assert body["task"]["id"] == live.backend.task_id
    expect = {
        "start": ("start", None),
        "spec-answers": ("spec_answers", {"Q1": "yes"}),
        "spec-ok": ("spec_ok",),
        "send": ("send", "hello"),
        "ship": ("ship",),
        "close": ("close",),
        "cancel": ("cancel",),
        "lesson-approve": ("lesson_approve", "L1"),
        "go": ("go",),
        "rerun": ("rerun",),
        "wont": ("wont",),
        "done-manually": ("done_manually",),
        "model": ("model", "claude-fable-5-2"),
    }[action]
    assert live.backend.calls == [(expect[0], live.backend.task_id, *expect[1:])]


def test_empty_body_counts_as_empty_object(live: Live) -> None:
    r = call(live.port, "POST", f"/api/task/{live.backend.task_id}/ship", None, live.post_headers())
    assert r.status == 200


@pytest.mark.parametrize(
    "hdr",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "-"},
        {"X-Todoimpl-Token": "wrong"},
        {"X-Todoimpl-Token": "-"},
    ],
)
def test_post_without_origin_or_token_is_403_and_does_nothing(live: Live, hdr: dict[str, str]) -> None:
    r = post(live, "ship", {}, **hdr)
    assert r.status == 403
    validate("response", r.json())
    assert r.json()["error"]["code"] == "forbidden"
    assert live.backend.calls == []


def test_forbidden_post_does_not_poison_a_keepalive_connection(live: Live) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", live.port, timeout=5)
    conn.request("POST", "/api/task/abcdefgh-0/send", body=b'{"text": "x"}', headers={"Origin": "http://bad"})
    first = conn.getresponse()
    first.read()
    conn.request("GET", "/version")
    second = conn.getresponse()
    assert (first.status, second.status) == (403, 200)
    assert json.loads(second.read())["build"] == "abc1234"
    conn.close()


def test_oversized_body_is_refused_unread(live: Live) -> None:
    r = post(live, "lesson-approve", {"lesson_id": "x" * 300_000})  # `send` has the 40 MB cap (T2322)
    assert r.status == 400
    assert "too large" in r.json()["error"]["message"]
    assert live.backend.calls == []


@pytest.mark.parametrize("length", ["abc", "-5"])
def test_bad_content_length_is_400(live: Live, length: str) -> None:
    r = post(live, "ship", b"{}", **{"Content-Length": length})
    assert r.status == 400


@pytest.mark.parametrize("body", ["[]", "not json", '"str"', b"\xff\xfe"])
def test_non_object_or_invalid_json_is_400(live: Live, body: Any) -> None:
    r = post(live, "ship", body)
    assert r.status == 400
    assert r.json()["error"]["code"] == "bad_request"


@pytest.mark.parametrize(
    ("action", "body"),
    [
        ("ship", {"surprise": 1}),
        ("spec-answers", {}),
        ("spec-answers", {"answers": {}}),
        ("spec-answers", {"answers": {"x": "a"}}),
        ("spec-answers", {"answers": {"Q1": ""}}),
        ("spec-answers", {"answers": {"Q1": 3}}),
        ("spec-answers", {"answers": []}),
        ("spec-answers", {"answers": {"Q1": "a"}, "more": 1}),
        ("send", {}),
        ("send", {"text": ""}),
        ("send", {"text": 5}),
        ("send", {"text": "x" * 20001}),
        ("lesson-approve", {}),
        ("lesson-approve", {"lesson_id": ""}),
        ("lesson-approve", {"lesson_id": 1}),
        ("model", {}),
        ("model", {"model": "gpt-5"}),
        ("model", {"model": "claude-fable-5-2", "more": 1}),
    ],
)
def test_body_must_match_requests_schema(live: Live, action: str, body: dict[str, Any]) -> None:
    r = post(live, action, body)
    assert r.status == 400
    assert live.backend.calls == []


def test_unknown_action_and_task_on_post(live: Live) -> None:
    assert post(live, "explode").status == 404
    r = call(live.port, "POST", "/api/task/zzzzzzzz-0/ship", {}, live.post_headers())
    assert r.status == 404
    assert call(live.port, "POST", "/api/task/short/ship", {}, live.post_headers()).status == 400
    assert call(live.port, "POST", "/elsewhere", {}, live.post_headers()).status == 404


def test_disabled_action_is_409_with_its_reason(live: Live) -> None:
    for action in live.backend.task_data["card"]["actions"]:
        if action["id"] == "ship":
            action.update(enabled=False, reason="not at the gate")
    r = post(live, "ship")
    assert r.status == 409
    validate("response", r.json())
    assert r.json()["error"] == {"code": "disabled", "message": "not at the gate"}
    assert live.backend.calls == []


def test_action_missing_from_card_is_409(live: Live) -> None:
    live.backend.task_data["card"]["actions"] = []
    r = post(live, "ship")
    assert r.status == 409
    assert r.json()["error"]["code"] == "disabled"


def test_disabled_action_without_reason_still_answers(live: Live) -> None:
    live.backend.task_data["card"]["actions"] = [
        {"id": "ship", "label": "s", "enabled": False, "reason": None}
    ]
    assert post(live, "ship").json()["error"]["message"]


def test_backend_error_on_post_keeps_its_code(live: Live) -> None:
    class Gone(FakeBackend):
        def ship(self, id8: str) -> None:
            raise BackendError("conflict", "push refused")

    live.server.router.backend = Gone()
    r = post(live, "ship")
    assert r.status == 409
    assert r.json()["error"] == {"code": "conflict", "message": "push refused"}


def test_unexpected_post_exception_is_500(live: Live) -> None:
    class Bad(FakeBackend):
        def ship(self, id8: str) -> None:
            raise OSError("disk")

    live.server.router.backend = Bad()
    r = post(live, "ship")
    assert r.status == 500
    assert r.json()["error"]["code"] == "internal"


def test_card_falls_back_when_the_task_vanishes_after_the_action(live: Live) -> None:
    class Vanishing(FakeBackend):
        def __init__(self) -> None:
            super().__init__()
            self.reads = 0

        def task(self, id8: str) -> dict[str, Any] | None:
            self.reads += 1
            return super().task(id8) if self.reads == 1 else None

    live.server.router.backend = Vanishing()
    r = post(live, "ship")
    assert r.status == 200
    assert r.json()["task"]["id"] == live.backend.task_id


def test_start_that_lost_the_race_to_an_auto_start_returns_the_card_without_error(live: Live) -> None:
    card = live.backend.task_data["card"]
    card["actions"] = [a for a in card["actions"] if a["id"] != "start"]
    card["auto_start"] = {"reason": "done_check", "passed_at": 1.0}
    r = post(live, "start", {})
    assert r.status == 200, r.body
    validate("response", r.json())
    assert live.backend.calls == []


def test_start_not_offered_without_an_auto_start_is_still_refused(live: Live) -> None:
    card = live.backend.task_data["card"]
    card["actions"] = [a for a in card["actions"] if a["id"] != "start"]
    r = post(live, "start", {})
    assert r.status == 409
