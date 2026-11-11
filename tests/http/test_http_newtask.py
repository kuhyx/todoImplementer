"""POST /api/new-task: kuhy's own task with images, then the repo card's own Start click."""

import base64
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from jsonschema import ValidationError
from todoimpl.http.backend import BackendError
from todoimpl.http.newtask import MAX_IMAGE, MAX_IMAGES, NewTask

JPEG = b"\xff\xd8\xff\xe0pixels"
B64 = base64.b64encode(JPEG).decode()


class FakeNewTasks:
    def __init__(self, card: str) -> None:
        self.card = card
        self.calls: list[NewTask] = []
        self.fail: BackendError | None = None

    def create(self, task: NewTask) -> tuple[str, str]:
        self.calls.append(task)
        if self.fail is not None:
            raise self.fail
        return "abcd1234", self.card


@pytest.fixture
def made(live: Live) -> FakeNewTasks:
    fake = FakeNewTasks(live.backend.task_id)
    live.backend.new_task_service = fake  # type: ignore[attr-defined]
    return fake


def post(live: Live, body: Any, **hdr: str) -> Any:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    return call(live.port, "POST", "/api/new-task", body, headers)


def good(**over: Any) -> dict[str, Any]:
    return {"repo": "kuhyx/demo", "title": "Fix it", "body": "see pic", "images": [{"data_b64": B64}], **over}


def test_creates_then_starts_the_card_and_answers_the_contract(live: Live, made: FakeNewTasks) -> None:
    validate("requests", good(), "new_task")
    r = post(live, good())
    assert r.status == 200, r.body
    validate("response", r.json())
    assert r.json()["note"] == "abcd1234"
    assert r.json()["started"] is True
    assert made.calls == [NewTask("kuhyx/demo", "Fix it", "see pic", (JPEG,))]
    assert live.backend.calls == [("start", live.backend.task_id, None)]


def test_repo_and_title_alone_are_enough(live: Live, made: FakeNewTasks) -> None:
    body = {"repo": "kuhyx/demo", "title": "  Fix it  "}
    validate("requests", body, "new_task")
    assert post(live, body).status == 200
    assert made.calls == [NewTask("kuhyx/demo", "Fix it", "", ())]


def test_a_card_that_cannot_start_now_still_answers_ok_with_the_card(live: Live, made: FakeNewTasks) -> None:
    for action in live.backend.task_data["card"]["actions"]:
        if action["id"] == "start":
            action.update(enabled=False, reason="already running")
    r = post(live, good())
    assert r.status == 200, r.body
    validate("response", r.json())
    assert r.json()["started"] is False
    assert r.json()["task"]["id"] == live.backend.task_id
    assert live.backend.calls == []


def test_a_card_gone_after_the_add_is_not_found(live: Live, made: FakeNewTasks) -> None:
    made.card = "zzzzzzzz-0"
    r = post(live, good())
    assert r.status == 404
    assert "zzzzzzzz-0" in r.json()["error"]["message"]


def test_the_service_refusal_reaches_the_page(live: Live, made: FakeNewTasks) -> None:
    made.fail = BackendError("conflict", "an open part is already called Fix it")
    r = post(live, good())
    assert (r.status, r.json()["error"]["code"]) == (409, "conflict")


def test_without_a_service_the_route_does_not_exist(live: Live) -> None:
    assert post(live, good()).status == 404


@pytest.mark.parametrize(
    ("body", "why"),
    [
        ("[]", "JSON object"),
        ({"title": "x"}, "repo, title"),
        (good(extra=1), "repo, title"),
        (good(repo="demo"), "owner/name"),
        (good(repo=5), "owner/name"),
        (good(title=""), "title"),
        (good(title="   "), "title"),
        (good(title="a\n## b"), "title"),
        (good(title="x" * 201), "title"),
        (good(title=3), "title"),
        (good(body=3), "body"),
        (good(body="x" * 20001), "body"),
        (good(images={}), "images"),
        (good(images=[{"data_b64": B64}] * (MAX_IMAGES + 1)), "images"),
        (good(images=["x"]), "image 1"),
        (good(images=[{"data_b64": B64, "x": 1}]), "image 1"),
        (good(images=[{"data_b64": 5}]), "image 1"),
        (good(images=[{"data_b64": "%%%"}]), "base64"),
        (good(images=[{"data_b64": base64.b64encode(b"\x89PNG....").decode()}]), "JPEG"),
        (good(images=[{"data_b64": base64.b64encode(JPEG + b"0" * MAX_IMAGE).decode()}]), "6 MB"),
    ],
)
def test_bad_bodies_are_400_and_create_nothing(live: Live, made: FakeNewTasks, body: Any, why: str) -> None:
    r = post(live, body)
    assert r.status == 400, r.body
    assert why in r.json()["error"]["message"]
    assert made.calls == []


def test_the_contract_refuses_what_the_server_refuses() -> None:
    for bad in (good(repo="demo"), good(title="a\nb"), good(title=" "), good(images=[{}]), good(extra=1)):
        with pytest.raises(ValidationError):
            validate("requests", bad, "new_task")


def test_a_big_request_fits_but_one_over_the_cap_is_refused_unread(live: Live, made: FakeNewTasks) -> None:
    big = base64.b64encode(JPEG + b"0" * (MAX_IMAGE - len(JPEG))).decode()
    assert (
        post(live, good(images=[{"data_b64": big}] * 4)).status == 200
    )  # ~32 MB of base64, over the old cap
    r = post(live, b"{}", **{"Content-Length": str(40 * 1024 * 1024 + 1)})
    assert r.status == 400
    assert "40960 KB" in r.json()["error"]["message"]


def test_a_post_without_the_token_is_forbidden(live: Live, made: FakeNewTasks) -> None:
    assert post(live, good(), **{"X-Todoimpl-Token": "-"}).status == 403
    assert made.calls == []
