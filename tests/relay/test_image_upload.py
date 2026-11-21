"""The app sends any number of images (T2426): each goes up alone as `image_upload`, named by its id."""

import base64

from relayfakes import answer, board_handlers, req
from rtdb_relay.tests._fake_rtdb import FakeRtdb
from todoimpl.http.routes import Router
from todoimpl.newtask import noteimages, uploads

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def test_t2426_an_image_upload_is_staged_and_answers_its_id(fake: FakeRtdb, router: Router) -> None:
    body = {"data_b64": base64.b64encode(PNG).decode()}
    [result] = answer(fake, board_handlers(router), [req("image_upload", body)])
    assert result["ok"] is True
    upload = result["data"]["upload"]
    assert upload["size"] == len(PNG)
    assert upload["name"] == "image.png"
    claimed = uploads.claim([upload["id"]], uploads.root())
    assert not isinstance(claimed, str)
    assert claimed[0].path.read_bytes() == PNG


def test_t2426_a_non_image_or_bad_base64_is_refused(fake: FakeRtdb, router: Router) -> None:
    bad = [req("image_upload", {"data_b64": base64.b64encode(b"hello world").decode()})]
    bad.append(req("image_upload", {"data_b64": "%%%%"}))
    big = PNG + b"0" * noteimages.MAX_INLINE
    bad.append(req("image_upload", {"data_b64": base64.b64encode(big).decode()}))
    results = answer(fake, board_handlers(router), bad)
    assert [(r["ok"], r["code"]) for r in results] == [(False, "bad_request")] * 3


def test_t2426_more_than_eight_images_are_fine() -> None:
    refs = noteimages.parse([{"upload": f"{i:032x}"} for i in range(40)])
    assert len(refs) == 40
