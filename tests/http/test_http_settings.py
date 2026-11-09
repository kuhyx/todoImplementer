"""POST /api/settings/credits-fallback: the usual CSRF and Origin gate, a strict body, the contract answer."""

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call


def post_setting(live: Live, body: Any, **hdr: str) -> Any:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    return call(live.port, "POST", "/api/settings/credits-fallback", body, headers)


@pytest.mark.parametrize("enabled", [True, False])
def test_t1855_toggle_stores_the_setting_and_answers_the_credits_object(live: Live, enabled: bool) -> None:
    r = post_setting(live, {"enabled": enabled})
    assert r.status == 200, r.body
    body = r.json()
    validate("response", body)
    assert body["ok"] is True
    assert body["credits"]["enabled"] is enabled
    assert live.backend.calls == [("set_credits_fallback", str(enabled))]
    validate("requests", {"enabled": enabled}, "credits_fallback")


@pytest.mark.parametrize(
    "hdr",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "-"},
        {"X-Todoimpl-Token": "wrong"},
        {"X-Todoimpl-Token": "-"},
    ],
)
def test_t1855_toggle_needs_origin_and_token(live: Live, hdr: dict[str, str]) -> None:
    r = post_setting(live, {"enabled": False}, **hdr)
    assert r.status == 403
    assert live.backend.calls == []


@pytest.mark.parametrize("body", [{}, {"enabled": "yes"}, {"enabled": True, "x": 1}, "[true]", "nope"])
def test_toggle_refuses_a_bad_body(live: Live, body: Any) -> None:
    r = post_setting(live, body)
    assert r.status == 400
    validate("response", r.json())
    assert live.backend.calls == []


def test_toggle_refuses_an_empty_body(live: Live) -> None:
    r = call(live.port, "POST", "/api/settings/credits-fallback", None, live.post_headers())
    assert r.status == 400
