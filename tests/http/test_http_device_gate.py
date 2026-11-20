"""Public requests need a paired device; local requests behave as before (DOCS-phone.md)."""

import pytest
from httpfakes import INDEX, Live, call
from phonehttpfakes import PUBLIC, pair, public, public_post, raw_get
from todoimpl.http.device_gate import device_tokens, is_local

PORT = 8786
PAGES = ["/", "/usage", "/sessions", "/_astro/app.js"]
APIS = ["/api/board", "/version", "/api/usage", "/api/sessions", "/api/nope", "/nothing"]


@pytest.mark.parametrize(
    "host",
    ["127.0.0.1:8786", "localhost:8786", "[::1]:8786", "LOCALHOST:8786", "LocalHost:8786"],
)
def test_local_hosts(host: str) -> None:
    assert is_local(host, PORT)


@pytest.mark.parametrize(
    "host",
    [
        None,
        "",
        PUBLIC,
        "evil.com",
        "127.0.0.1",
        "localhost",
        "[::1]",
        "127.0.0.1:8787",
        "127.0.0.1:",
        "127.0.0.1:08786",
        " 127.0.0.1:8786",
        "127.0.0.1:8786 ",
        "127.0.0.1:8786.evil.com",
        "evil.com:8786",
        "evil.com@127.0.0.1:8786",
        "127.0.0.1:8786,evil.com",
        "0.0.0.0:8786",
        "[::ffff:127.0.0.1]:8786",
    ],
)
def test_everything_else_is_public(host: str | None) -> None:
    assert not is_local(host, PORT)


def test_cookie_headers_are_split_and_junk_is_ignored() -> None:
    lines = ["a=1; todoimpl_device=abc; b=2", "todoimpl_device=def", "todoimpl_device", "x; todoimpl_device="]
    assert device_tokens(lines) == ["abc", "def"]
    assert device_tokens([]) == []
    assert device_tokens(["todoimpl_device=" + "x" * 500]) == []


@pytest.mark.parametrize("path", [*PAGES, *APIS])
def test_public_get_without_cookie_is_401(live: Live, path: str) -> None:
    r = public(live, "GET", path)
    assert r.status == 401
    assert r.json() == {"error": "unauthorized"}
    assert r.headers["cache-control"] == "no-store"


def test_public_live_stream_without_cookie_is_401(live: Live) -> None:
    r = public(live, "GET", f"/api/live?id={live.backend.task_id}")
    assert r.status == 401
    assert "text/event-stream" not in r.headers["content-type"]


def test_public_post_without_cookie_is_401_even_with_good_csrf(live: Live) -> None:
    r = public_post(live, f"/api/task/{live.backend.task_id}/start")
    assert r.status == 401
    assert live.backend.calls == []
    assert public_post(live, "/api/settings/credits-fallback").status == 401
    assert public_post(live, "/api/pair").status == 403


@pytest.mark.parametrize(
    "forged",
    [
        {"X-Forwarded-For": "127.0.0.1"},
        {"X-Real-IP": "127.0.0.1"},
        {"X-Forwarded-Host": "127.0.0.1:8786", "Forwarded": "for=127.0.0.1;host=127.0.0.1"},
        {"X-Forwarded-For": "::1", "X-Real-IP": "::1", "Client-IP": "127.0.0.1"},
    ],
)
@pytest.mark.parametrize("path", ["/", "/api/board", "/version"])
def test_forged_forwarding_headers_do_not_make_a_request_local(
    live: Live, path: str, forged: dict[str, str]
) -> None:
    assert public(live, "GET", path, **forged).status == 401


def test_host_without_port_is_public(live: Live) -> None:
    r = call(live.port, "GET", "/api/board", None, {"Host": "127.0.0.1"})
    assert r.status == 401


def test_missing_host_is_public(live: Live) -> None:
    assert raw_get(live, "/api/board", "").startswith(b"HTTP/1.1 401")


def test_two_host_headers_are_public(live: Live) -> None:
    lines = f"Host: 127.0.0.1:{live.port}\r\nHost: {PUBLIC}\r\n"
    assert raw_get(live, "/api/board", lines).startswith(b"HTTP/1.1 401")


def test_absolute_form_target_is_never_local(live: Live) -> None:
    lines = f"Host: 127.0.0.1:{live.port}\r\n"
    assert raw_get(live, f"http://127.0.0.1:{live.port}/api/board", lines).startswith(b"HTTP/1.1 401")


@pytest.mark.parametrize("path", ["/api/board", "/version", "/", "/api/usage"])
def test_local_requests_need_no_cookie(live: Live, path: str) -> None:
    assert call(live.port, "GET", path).status == 200
    assert call(live.port, "GET", path, None, {"Host": f"localhost:{live.port}"}).status == 200
    assert call(live.port, "GET", path, None, {"Host": f"[::1]:{live.port}"}).status == 200


def test_local_post_is_unchanged(live: Live) -> None:
    r = call(live.port, "POST", f"/api/task/{live.backend.task_id}/start", {}, live.post_headers())
    assert r.status == 200
    assert call(live.port, "POST", "/api/task/x/start", {}, {"Origin": live.origin}).status == 403


def test_local_with_a_bad_cookie_is_still_local(live: Live) -> None:
    assert call(live.port, "GET", "/api/board", None, {"Cookie": "todoimpl_device=junk"}).status == 200


def test_paired_cookie_opens_the_public_api(live: Live) -> None:
    token = pair(live)
    assert public(live, "GET", "/api/board", token).status == 200
    assert public(live, "GET", "/version", token).status == 200
    assert public(live, "GET", "/sessions", token).status in {200, 404}
    assert public(live, "GET", f"/api/live?id={live.backend.task_id}", token).status == 200
    done = public_post(live, f"/api/task/{live.backend.task_id}/start", token)
    assert done.status == 200
    assert live.backend.calls[-1][0] == "start"


def test_paired_cookie_still_needs_origin_and_csrf_on_posts(live: Live) -> None:
    token = pair(live)
    path = f"/api/task/{live.backend.task_id}/start"
    headers = {"Host": PUBLIC, "Cookie": f"todoimpl_device={token}", "Content-Type": "application/json"}
    assert call(live.port, "POST", path, {}, headers).status == 403
    good = {**live.post_headers(), **headers, "X-Todoimpl-Token": "wrong"}
    assert call(live.port, "POST", path, {}, good).status == 403
    assert live.backend.calls == []


@pytest.mark.parametrize("kind", ["append", "truncate", "swapcase", "empty", "huge"])
def test_tampered_cookie_is_401(live: Live, kind: str) -> None:
    token = pair(live)
    tampered = {
        "append": token + "x",
        "truncate": token[:-1],
        "swapcase": token.swapcase(),
        "empty": "",
        "huge": "x" * 500,
    }[kind]
    assert public(live, "GET", "/api/board", tampered).status == 401


def test_the_cookie_name_must_match_exactly(live: Live) -> None:
    token = pair(live)
    r = public(live, "GET", "/api/board", Cookie=f"todoimpl_devic={token}; x_todoimpl_device={token}")
    assert r.status == 401


def test_a_valid_cookie_among_other_cookies_works(live: Live) -> None:
    token = pair(live)
    cookies = f"a=b; todoimpl_device=junk; todoimpl_device={token}; c=d"
    assert public(live, "GET", "/api/board", Cookie=cookies).status == 200


def test_deleting_the_device_file_revokes_the_phone(live: Live) -> None:
    token = pair(live)
    assert public(live, "GET", "/api/board", token).status == 200
    live.server.gate.store.path.unlink()
    assert public(live, "GET", "/api/board", token).status == 401


@pytest.mark.parametrize(
    "path",
    [
        "/pair",
        "/manifest.webmanifest",
        "/favicon.svg",
        "/icons/icon-192.png",
        "/icons/a.b-c_d.png",
        "/icons/x.svg",
    ],
)
def test_exemptions_are_reachable_without_a_cookie(live: Live, path: str) -> None:
    (live.dist / "icons").mkdir(exist_ok=True)
    for name in ("icon-192.png", "a.b-c_d.png", "x.svg"):
        (live.dist / "icons" / name).write_bytes(b"png")
    (live.dist / "manifest.webmanifest").write_text("{}", encoding="utf-8")
    (live.dist / "favicon.svg").write_text("<svg/>", encoding="utf-8")
    r = public(live, "GET", path)
    assert r.status != 401
    assert r.status in {200, 403}  # /pair without a code is 403, the rest are served


@pytest.mark.parametrize(
    "path",
    [
        "/icons/../index.html",
        "/icons/%2e%2e/index.html",
        "/icons/..%2findex.html",
        "/icons/sub/x.png",
        "/icons/",
        "/icons",
        "/icons/.hidden",
        "/icons/x.html",
        "/icons/x.png.html",
        "/icons/x",
        "/pair/",
        "/pair/x",
        "/manifest.webmanifest/x",
        "/favicon.svg/",
        "/Pair",
        "//icons/../index.html",
        "/api/icons/x.png",
    ],
)
def test_nothing_else_is_exempt_and_exemptions_cannot_be_walked_out_of(live: Live, path: str) -> None:
    (live.dist / "icons").mkdir(exist_ok=True)
    (live.dist / "icons" / "x.png").write_bytes(b"png")
    (live.dist / "icons" / "x.html").write_text(INDEX, encoding="utf-8")
    r = public(live, "GET", path)
    assert r.status == 401
    assert live.token not in r.body.decode()


def test_exemptions_are_get_only(live: Live) -> None:
    assert public_post(live, "/pair").status == 401
    assert public_post(live, "/icons/x.png").status == 401


def test_unsupported_methods_still_get_nothing(live: Live) -> None:
    assert public(live, "PUT", "/api/board").status == 501
