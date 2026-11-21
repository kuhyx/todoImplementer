"""At night (DOCS-phone.md "Night") the phone is locked out: every public request gets 423; the PC is not."""

import pytest
from httpfakes import Live, call
from phonehttpfakes import pair, public, public_post


@pytest.fixture
def asleep(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_NIGHT", "00:00-23:59")


def test_a_paired_phone_is_locked_out_at_night(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    token = pair(live)
    monkeypatch.setenv("TODOIMPL_NIGHT", "00:00-23:59")
    for path in ["/", "/api/board", "/pair?c=x", "/manifest.webmanifest"]:
        reply = public(live, "GET", path, token)
        assert reply.status == 423, path
        assert reply.body == b""
        assert int(reply.headers["retry-after"]) > 0
    assert public_post(live, "/api/refresh", token).status == 423


@pytest.mark.usefixtures("asleep")
def test_the_pc_keeps_working_at_night(live: Live) -> None:
    assert call(live.port, "GET", "/api/board").status == 200


def test_by_day_the_phone_works(live: Live) -> None:
    token = pair(live)
    assert public(live, "GET", "/api/board", token).status == 200
