"""Pairing flow over a real socket: mint on the PC, scan on the phone, cookie, renewal, page flag."""

import json
import stat
from urllib.parse import parse_qs, urlsplit

import pytest
from contract_lib import validate
from httpfakes import INDEX, Live, call
from phonehttpfakes import COOKIE, PUBLIC, mint_url, pair, public, public_post, token_of

ORIGIN = "https://agents.kuhy.duckdns.org"


def code_of(url: str) -> str:
    return parse_qs(urlsplit(url).query)["c"][0]


def test_mint_is_local_only_and_matches_the_contract(live: Live) -> None:
    r = call(live.port, "POST", "/api/pair", {}, live.post_headers())
    assert r.status == 200
    body = r.json()
    validate("pair", body)
    assert body["url"].startswith(f"{ORIGIN}/pair?c=")
    assert r.headers["cache-control"] == "no-store"
    assert body["expires_at"] > 1_700_000_000


def test_mint_needs_the_csrf_token_and_origin(live: Live) -> None:
    good = live.post_headers()
    assert call(live.port, "POST", "/api/pair", {}, {**good, "X-Todoimpl-Token": "-"}).status == 403
    assert (
        call(live.port, "POST", "/api/pair", {}, {k: v for k, v in good.items() if k != "Origin"}).status
        == 403
    )
    assert call(live.port, "POST", "/api/pair", {}, {**good, "Origin": "https://evil.example"}).status == 403
    assert call(live.port, "POST", "/api/pair", {}, {"Origin": live.origin}).status == 403


def test_mint_with_a_body_does_not_poison_the_connection(live: Live) -> None:
    r = call(live.port, "POST", "/api/pair", b"x" * 1000, live.post_headers())
    assert r.status == 200


def test_mint_over_a_public_host_is_403_even_for_a_paired_phone(live: Live) -> None:
    token = pair(live)
    r = public_post(live, "/api/pair", token)
    assert r.status == 403
    assert r.body == b""


def test_get_on_the_mint_route_is_not_a_route(live: Live) -> None:
    assert call(live.port, "GET", "/api/pair").status == 404


def test_redeem_sets_the_exact_cookie_and_redirects(live: Live) -> None:
    code = code_of(mint_url(live))
    r = public(live, "GET", f"/pair?c={code}", **{"User-Agent": "Pixel"})
    assert r.status == 303
    assert r.headers["location"] == "/"
    assert r.headers["cache-control"] == "no-store"
    token = token_of(r)
    assert r.headers["set-cookie"] == (
        f"{COOKIE}={token}; Max-Age=34560000; Path=/; Secure; HttpOnly; SameSite=Lax"
    )
    assert len(token) >= 43


def test_a_code_works_once(live: Live) -> None:
    code = code_of(mint_url(live))
    assert public(live, "GET", f"/pair?c={code}").status == 303
    again = public(live, "GET", f"/pair?c={code}")
    assert again.status == 403
    assert "set-cookie" not in again.headers


@pytest.mark.parametrize("query", ["", "?c=", "?c=nope", "?x=1", "?c=a&c=b", "?c=%FF%FE", "?C=abc"])
def test_bad_or_missing_codes_are_403(live: Live, query: str) -> None:
    mint_url(live)
    r = public(live, "GET", f"/pair{query}")
    assert r.status == 403
    assert "set-cookie" not in r.headers
    assert len(r.body) < 40


def test_two_codes_in_the_query_are_refused_even_if_one_is_good(live: Live) -> None:
    code = code_of(mint_url(live))
    assert public(live, "GET", f"/pair?c={code}&c={code}").status == 403
    assert public(live, "GET", f"/pair?c={code}").status == 303


def test_an_expired_code_is_403(live: Live) -> None:
    now = [1_900_000_000.0]
    live.server.gate.codes.clock = lambda: now[0]
    code = code_of(mint_url(live))
    now[0] += 301
    assert public(live, "GET", f"/pair?c={code}").status == 403


def test_the_sixth_pending_code_evicts_the_oldest(live: Live) -> None:
    codes = [code_of(mint_url(live)) for _ in range(6)]
    assert public(live, "GET", f"/pair?c={codes[0]}").status == 403
    assert public(live, "GET", f"/pair?c={codes[1]}").status == 303


def test_redeeming_on_the_pc_also_works(live: Live) -> None:
    code = code_of(mint_url(live))
    assert call(live.port, "GET", f"/pair?c={code}").status == 303


def test_the_cookie_then_opens_the_api_and_the_store_holds_no_secret(live: Live) -> None:
    token = pair(live, ua="Pixel/6a " + "z" * 100)
    assert public(live, "GET", "/api/board", token).status == 200
    path = live.server.gate.store.path
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    text = path.read_text(encoding="utf-8")
    assert token not in text
    (entry,) = json.loads(text)
    assert set(entry) == {"sha256", "created", "last_seen", "ua"}
    assert entry["ua"] == ("Pixel/6a " + "z" * 100)[:80]


def test_each_pairing_adds_a_device(live: Live) -> None:
    first, second = pair(live), pair(live)
    assert first != second
    assert len(json.loads(live.server.gate.store.path.read_text(encoding="utf-8"))) == 2


def test_public_pages_renew_the_cookie_with_the_same_token(live: Live) -> None:
    token = pair(live)
    r = public(live, "GET", "/", token)
    assert r.status == 200
    assert r.headers["set-cookie"] == (
        f"{COOKIE}={token}; Max-Age=34560000; Path=/; Secure; HttpOnly; SameSite=Lax"
    )


def test_api_and_assets_do_not_renew(live: Live) -> None:
    token = pair(live)
    assert "set-cookie" not in public(live, "GET", "/api/board", token).headers
    assert "set-cookie" not in public(live, "GET", "/_astro/app.js", token).headers
    assert "set-cookie" not in call(live.port, "GET", "/").headers


def test_subpages_renew_too(live: Live) -> None:
    (live.dist / "usage").mkdir()
    (live.dist / "usage" / "index.html").write_text(INDEX, encoding="utf-8")
    token = pair(live)
    assert "set-cookie" in public(live, "GET", "/usage", token).headers


def test_the_local_flag_is_in_local_html_only(live: Live) -> None:
    meta = '<meta name="todoimpl-local" content="1">'
    token = pair(live)
    assert meta in call(live.port, "GET", "/").body.decode()
    assert meta in call(live.port, "GET", "/", None, {"Host": f"localhost:{live.port}"}).body.decode()
    page = public(live, "GET", "/", token).body.decode()
    assert "todoimpl-local" not in page
    assert 'name="todoimpl-csrf"' in page


def test_a_shipped_page_cannot_claim_to_be_local(live: Live) -> None:
    claim = '<meta name="todoimpl-local" content="1">'
    (live.dist / "index.html").write_text(
        f"<html><head>{claim}<title>t</title></head></html>", encoding="utf-8"
    )
    token = pair(live)
    assert "todoimpl-local" not in public(live, "GET", "/", token).body.decode()
    assert call(live.port, "GET", "/").body.decode().count("todoimpl-local") == 1


def test_the_public_origin_can_be_overridden(monkeypatch: pytest.MonkeyPatch, live: Live) -> None:
    from todoimpl.http.device_gate import Gate  # noqa: PLC0415 - needs the env set first

    monkeypatch.setenv("TODOIMPL_PUBLIC_ORIGIN", "https://other.example")
    gate = Gate.create(live.port)
    assert gate.public_origin == "https://other.example"
    assert PUBLIC not in gate.public_origin
