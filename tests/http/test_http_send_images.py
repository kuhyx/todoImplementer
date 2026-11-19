"""POST /api/task/<id>/send with images: `image_ref` items (an upload id, or inline bytes for the phone)."""

import base64
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call, post
from jsonschema import ValidationError
from todoimpl.newtask import noteimages

PNG = b"\x89PNG\r\n\x1a\n" + b"png"
ID1, ID2 = "a" * 32, "b" * 32


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_t2320_send_hands_the_upload_ids_to_the_backend_in_order(live: Live) -> None:
    body = {"text": "see [Image #1] and [Image #2]", "images": [{"upload": ID1}, {"upload": ID2}]}
    validate("requests", body, "send")
    r = post(live, "send", body)
    assert r.status == 200, r.body
    assert live.backend.calls == [("send", live.backend.task_id, body["text"], (ID1, ID2))]


def test_t2322_send_takes_inline_bytes_and_a_body_over_256_kb(live: Live) -> None:
    data = PNG + b"0" * (400 * 1024)
    body = {"text": "phone shot [Image #1]", "images": [{"data_b64": b64(data)}]}
    validate("requests", body, "send")
    r = post(live, "send", body)
    assert r.status == 200, r.body
    assert live.backend.calls == [("send", live.backend.task_id, body["text"], (data,))]


@pytest.mark.parametrize(
    ("images", "why"),
    [
        ({}, "images must be a list of at most 8"),
        ([{"upload": ID1}] * 2, "image 2 repeats an upload"),
        ([{"upload": f"{i:032x}"} for i in range(9)], "images must be a list of at most 8"),
        (["x"], "image 1 must be {upload} or {data_b64}"),
        ([{"upload": "../x"}], "image 1 must be {upload} or {data_b64}"),
        ([{"upload": ID1, "data_b64": b64(PNG)}], "image 1 must be {upload} or {data_b64}"),
        ([{"data_b64": 5}], "image 1 must be {upload} or {data_b64}"),
        ([{"data_b64": "%%%"}], "image 1 is not base64"),
        ([{"data_b64": b64(b"%PDF-1.7")}], "image 1 is not a PNG, JPEG, WebP or GIF"),
        ([{"data_b64": b64(PNG + b"0" * noteimages.MAX_INLINE)}], "image 1 is over 6 MB"),
    ],
)
def test_t2320_bad_images_are_400_and_send_nothing(live: Live, images: Any, why: str) -> None:
    r = post(live, "send", {"text": "x", "images": images})
    assert r.status == 400, r.body
    assert why in r.json()["error"]["message"]
    assert live.backend.calls == []


@pytest.mark.parametrize(
    "images",
    [[{"upload": ID1}] * 9, [{"upload": "nope"}], [{"upload": ID1, "x": 1}], [{}], "x"],
)
def test_t2320_the_contract_refuses_what_the_server_refuses(images: Any) -> None:
    with pytest.raises(ValidationError):
        validate("requests", {"text": "x", "images": images}, "send")


def test_t2321_new_task_takes_upload_and_inline_image_refs_in_order(live: Live) -> None:
    made: list[Any] = []

    class Made:
        def create(self, task: Any) -> tuple[str, str]:
            made.append(task)
            return "abcd1234", live.backend.task_id

    live.backend.new_task_service = Made()  # type: ignore[attr-defined]
    body = {"repo": "kuhyx/demo", "title": "Fix", "images": [{"upload": ID1}, {"data_b64": b64(PNG)}]}
    validate("requests", body, "new_task")
    r = call(live.port, "POST", "/api/new-task", body, live.post_headers())
    assert r.status == 200, r.body
    assert made[0].images == (ID1, PNG)
