"""POST /api/upload: one attachment of any type streamed to the staging dir, before the new-task POST."""

from pathlib import Path
from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http import upload
from todoimpl.newtask import uploads


def send(live: Live, data: bytes, name: str | None = "report.pdf", **hdr: str) -> Any:
    headers = {**live.post_headers(), "Content-Type": "application/octet-stream", **hdr}
    if name is not None:
        headers[upload.NAME_HEADER] = name
    return call(live.port, "POST", upload.PATH, data, {k: v for k, v in headers.items() if v != "-"})


def staged() -> list[Path]:
    return sorted(p for p in uploads.root().rglob("*") if p.is_file())


def test_any_file_is_staged_byte_identical_and_answered_by_the_contract(live: Live) -> None:
    data = bytes(range(256)) * 1000
    r = send(live, data, "Q3%20report%20%C5%BC.PDF")
    assert r.status == 200, r.body
    validate("response", r.json())
    got = r.json()["upload"]
    assert got["name"] == "Q3 report ż.PDF"
    assert got["size"] == len(data)
    claimed = uploads.claim((got["id"],), uploads.root())
    assert not isinstance(claimed, str)
    (found,) = claimed
    assert found.path.read_bytes() == data
    assert found.name == "Q3 report ż.PDF"


@pytest.mark.parametrize(
    ("raw", "name"), [(None, "file"), ("../../etc/x.sh", "x.sh"), ("a\\b\\c", "c"), ("", "file")]
)
def test_names_lose_their_folders_and_a_missing_name_is_file(live: Live, raw: str | None, name: str) -> None:
    r = send(live, b"x", raw)
    assert r.json()["upload"]["name"] == name


def test_an_empty_file_and_an_odd_type_are_accepted(live: Live) -> None:
    assert send(live, b"", "weird.xyz").status == 200
    assert send(live, b"blob", "noext").status == 200


@pytest.mark.parametrize("hdr", [{"Origin": "http://evil.example"}, {"X-Todoimpl-Token": "-"}])
def test_a_foreign_origin_or_no_token_is_refused_and_stages_nothing(live: Live, hdr: dict[str, str]) -> None:
    r = send(live, b"payload", **hdr)
    assert r.status == 403
    assert staged() == []


def test_a_file_over_the_cap_is_refused_by_name_and_stages_nothing(
    live: Live, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(uploads, "MAX_FILE", 4)
    r = send(live, b"12345", "big.mov")
    assert r.status == 400
    assert "big.mov" in r.json()["error"]["message"]
    assert staged() == []


@pytest.mark.parametrize("length", ["x", "-1"])
def test_a_bad_length_is_refused(length: str) -> None:
    headers = {"Origin": "o", "X-Todoimpl-Token": "t", "Content-Length": length}
    assert upload.handle("t", ("o",), headers, lambda _n: b"").status == 400


def test_a_body_cut_short_stages_nothing() -> None:
    chunks = iter([b"abc", b""])
    headers = {"Origin": "o", "X-Todoimpl-Token": "t", "Content-Length": "10"}
    r = upload.handle("t", ("o",), headers, lambda _n: next(chunks))
    assert r.status == 400
    assert staged() == []


def test_a_full_disk_or_a_socket_timeout_is_internal_and_stages_nothing() -> None:
    def timeout(_n: int) -> bytes:
        raise TimeoutError

    headers = {"Origin": "o", "X-Todoimpl-Token": "t", "Content-Length": "10", upload.NAME_HEADER: "a.pdf"}
    r = upload.handle("t", ("o",), headers, timeout)
    assert r.status == 500
    assert "a.pdf" in r.body.decode()
    assert staged() == []
