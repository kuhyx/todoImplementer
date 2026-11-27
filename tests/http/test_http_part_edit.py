"""POST /api/task/<card>/part-edit: strict body, the card's edit flag decides, fresh card back (856c0f0a)."""

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http.backend import BackendError

PART = "aaaa1111-0"


class FakeParts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail: BackendError | None = None

    def edit(self, card: str, part: str, title: str, body: str) -> None:
        if self.fail:
            raise self.fail
        self.calls.append((card, part, title, body))


def _part(key: str, *, enabled: bool, reason: str | None = None) -> dict[str, Any]:
    edit = {"enabled": enabled, "reason": reason}
    return {"id": key, "title": "old", "state": "todo", "steps": None, "edit": edit, "body": "old text"}


@pytest.fixture
def parts(live: Live) -> FakeParts:
    fake = FakeParts()
    vars(live.backend)["part_service"] = fake  # FakeBackend has no such field: the route finds it by name
    live.backend.task_data["card"]["parts"] = [
        _part(PART, enabled=True),
        _part("bbbb2222-1", enabled=False, reason="ticked"),
    ]
    return fake


def post(live: Live, body: Any, card: str | None = None) -> tuple[int, Any]:
    path = f"/api/task/{card or live.backend.task_id}/part-edit"
    reply = call(live.port, "POST", path, body, live.post_headers())
    return reply.status, reply.json()


def test_an_offered_part_is_edited_and_the_fresh_card_comes_back(live: Live, parts: FakeParts) -> None:
    status, body = post(live, {"part": PART, "title": "  new title ", "body": "new text\n"})
    assert status == 200
    validate("response", body)
    assert parts.calls == [(live.backend.task_id, PART, "new title", "new text\n")]


def test_a_part_the_card_does_not_offer_is_refused_with_its_reason(live: Live, parts: FakeParts) -> None:
    status, body = post(live, {"part": "bbbb2222-1", "title": "t", "body": ""})
    assert (status, body["error"]) == (409, {"code": "disabled", "message": "ticked"})
    assert parts.calls == []


@pytest.mark.parametrize(
    ("sent", "card", "code"),
    [
        ({"part": "cccc3333-0", "title": "t", "body": ""}, None, "not_found"),  # no such part on the card
        ({"part": PART, "title": "t", "body": ""}, "ffff0000-0", "not_found"),  # no such card
        ({"part": PART, "title": "t"}, None, "bad_request"),
        ({"part": "nope", "title": "t", "body": ""}, None, "bad_request"),
        ({"part": PART, "title": " ", "body": ""}, None, "bad_request"),
        ({"part": PART, "title": "a\nb", "body": ""}, None, "bad_request"),
        ({"part": PART, "title": "x" * 201, "body": ""}, None, "bad_request"),
        ({"part": PART, "title": "t", "body": 3}, None, "bad_request"),
        ({"part": PART, "title": "t", "body": "x" * 20001}, None, "bad_request"),
        ("[]", None, "bad_request"),
    ],
)
def test_bad_requests_never_reach_the_service(
    live: Live, parts: FakeParts, sent: Any, card: str | None, code: str
) -> None:
    status, body = post(live, sent, card)
    assert body["error"]["code"] == code
    assert status in {400, 404}
    assert parts.calls == []


def test_a_refusal_of_the_service_reaches_the_page(live: Live, parts: FakeParts) -> None:
    parts.fail = BackendError("conflict", "section moved")
    status, body = post(live, {"part": PART, "title": "t", "body": ""})
    assert (status, body["error"]["message"]) == (409, "section moved")


def test_without_the_service_there_is_no_route(live: Live) -> None:
    status, body = post(live, {"part": PART, "title": "t", "body": ""})
    assert (status, body["error"]["code"]) == (404, "not_found")
