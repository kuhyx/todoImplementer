"""POST /api/task/<id>/ask/<verb>: gate, strict bodies, answers (C1-C7)."""
# ruff: noqa: PT018

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http.backend import BackendError

ID = "abcd1234-0"


class FakeAsks:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.fail: BackendError | None = None

    def _do(self, *args: Any) -> None:
        if self.fail:
            raise self.fail
        self.calls.append(args)

    def answer(self, id8: str, ask_id: str, option: str) -> None:
        self._do("answer", id8, ask_id, option)

    def take_recommended(self, id8: str) -> None:
        self._do("take", id8)

    def run_command(self, id8: str, ask_id: str, *, add: bool) -> dict[str, Any]:
        self._do("run", id8, ask_id, add)
        return {"exit": 0, "tail": "ok", "capped": False}

    def undo(self, id8: str, ask_id: str) -> None:
        self._do("undo", id8, ask_id)

    def verdict(self, id8: str, ask_id: str, *, approve: bool) -> None:
        self._do("verdict", id8, ask_id, approve)


@pytest.fixture
def asks(live: Live) -> FakeAsks:
    fake = FakeAsks()
    live.backend.ask_service = fake  # type: ignore[attr-defined]
    return fake


def post(live: Live, verb: str, body: Any, **hdr: str) -> tuple[int, Any]:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    reply = call(live.port, "POST", f"/api/task/{ID}/ask/{verb}", body, headers)
    return reply.status, reply.json()


def test_each_verb_reaches_the_service(live: Live, asks: FakeAsks) -> None:
    assert post(live, "answer", {"ask": "c1", "option": "red"})[0] == 200
    assert post(live, "take-recommended", {})[0] == 200
    status, body = post(live, "run", {"ask": "k1", "add": True})
    assert status == 200 and body["result"]["exit"] == 0
    assert post(live, "run", {"ask": "k1"})[0] == 200
    assert post(live, "undo", {"ask": "c1"})[0] == 200
    assert post(live, "approve", {"ask": "s1"})[0] == 200
    assert post(live, "reject", {"ask": "s1"})[0] == 200
    assert asks.calls == [
        ("answer", ID, "c1", "red"),
        ("take", ID),
        ("run", ID, "k1", True),
        ("run", ID, "k1", False),
        ("undo", ID, "c1"),
        ("verdict", ID, "s1", True),
        ("verdict", ID, "s1", False),
    ]


@pytest.mark.parametrize(
    ("verb", "body"),
    [
        ("answer", {"ask": "c1"}),
        ("answer", {"ask": "C1", "option": "x"}),
        ("answer", {"ask": "c1", "option": ""}),
        ("answer", {"ask": "c1", "option": "x", "extra": 1}),
        ("take-recommended", {"ask": "c1"}),
        ("run", {"ask": "k1", "add": "yes"}),
        ("undo", {}),
        ("approve", {"ask": 5}),
    ],
)
def test_bad_bodies_are_400(live: Live, asks: FakeAsks, verb: str, body: Any) -> None:
    assert post(live, verb, body)[0] == 400
    assert asks.calls == []


def test_not_json_is_400(live: Live, asks: FakeAsks) -> None:
    assert post(live, "undo", "{")[0] == 400


def test_refusal_is_a_contract_error(live: Live, asks: FakeAsks) -> None:
    asks.fail = BackendError("disabled", "run this one in a terminal")
    status, body = post(live, "run", {"ask": "k1"})
    assert status == 409 and body["error"]["message"] == "run this one in a terminal"
    validate("response", body)


def test_post_needs_the_csrf_token(live: Live, asks: FakeAsks) -> None:
    assert post(live, "undo", {"ask": "c1"}, **{"X-Todoimpl-Token": "bad"})[0] == 403


def test_without_a_service_the_route_is_not_found(live: Live) -> None:
    assert post(live, "undo", {"ask": "c1"})[0] == 404
