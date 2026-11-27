"""T2535: the app reads a note image over the relay (kind image_get), the same GET the page sends."""

from __future__ import annotations

import base64

from contract_lib import validate
from relayfakes import req
from todoimpl.http.reply import Reply
from todoimpl.relay import bridge, kinds


def test_t2535_image_get_maps_to_the_image_route_and_validates() -> None:
    call = kinds.ROUTED["image_get"].call({"folder": "3d6cd2ea-de63", "file": "1.jpg"})
    assert (call.method, call.target) == ("GET", "/api/image/3d6cd2ea-de63/1.jpg")
    assert kinds.lane_of("image_get") == "read"
    validate("relay-request", req("image_get", {"folder": "3d6cd2ea-de63", "file": "1.jpg"}))


def test_t2535_a_jpeg_answer_comes_back_as_base64_with_its_type() -> None:
    data = bridge.data_of(Reply(200, b"\xff\xd8\xffjpeg", "image/jpeg"))
    assert data == {"data_b64": base64.b64encode(b"\xff\xd8\xffjpeg").decode(), "type": "image/jpeg"}
    validate("relay-result", {"ok": True, "at": 1, "kind": "image_get", "data": data})
