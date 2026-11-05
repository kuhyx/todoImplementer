"""GET routes over a real socket (port 0), validated against contracts/*.schema.json."""

import threading
import time

import pytest
from contract_lib import validate
from httpfakes import INDEX, Live, call, post
from todoimpl.http.backend import BackendError
from todoimpl.version import __version__


def test_index_carries_csrf_and_build_meta(live: Live) -> None:
    r = call(live.port, "GET", "/")
    assert r.status == 200
    assert r.headers["content-type"].startswith("text/html")
    html = r.body.decode()
    assert f'name="todoimpl-csrf" content="{live.token}"' in html
    assert 'name="todoimpl-build" content="abc1234"' in html
    assert INDEX.split("<body>")[1] in html


def test_static_asset_and_missing_file(live: Live) -> None:
    ok = call(live.port, "GET", "/_astro/app.js")
    assert ok.status == 200
    assert ok.body == b"console.log(1)"
    assert ok.headers["x-content-type-options"] == "nosniff"
    missing = call(live.port, "GET", "/missing.png")
    assert missing.status == 404
    assert missing.json()["error"]["code"] == "not_found"


def test_version_matches_contract(live: Live) -> None:
    r = call(live.port, "GET", "/version")
    assert r.status == 200
    body = r.json()
    validate("version", body)
    assert body == {"build": "abc1234", "version": __version__}


def test_board_task_usage_match_contracts(live: Live) -> None:
    board = call(live.port, "GET", "/api/board")
    validate("board", board.json())
    assert board.headers["cache-control"] == "no-store"
    validate("task", call(live.port, "GET", f"/api/task/{live.backend.task_id}").json())
    validate("usage", call(live.port, "GET", "/api/usage").json())


def test_unknown_task_and_bad_id(live: Live) -> None:
    assert call(live.port, "GET", "/api/task/zzzzzzzz-0").status == 404
    bad = call(live.port, "GET", "/api/task/short")
    assert bad.status == 400
    assert bad.json()["error"]["code"] == "bad_request"


def test_unknown_api_path_is_404_json(live: Live) -> None:
    r = call(live.port, "GET", "/api/nothing")
    assert r.status == 404
    validate("response", {"ok": False, **r.json()})


def test_backend_failure_is_500_json_without_leaking(live: Live) -> None:
    live.backend.failure = RuntimeError("secret internals")
    r = call(live.port, "GET", "/api/board")
    assert r.status == 500
    assert r.json()["error"] == {"code": "internal", "message": "internal error"}
    assert b"secret" not in r.body


def test_backend_error_maps_to_its_status(live: Live) -> None:
    live.backend.failure = BackendError("conflict", "already shipping")
    r = call(live.port, "GET", "/api/usage")
    assert r.status == 409
    assert r.json()["error"] == {"code": "conflict", "message": "already shipping"}


def test_access_log_goes_to_logging_not_stderr(live: Live, capsys: pytest.CaptureFixture[str]) -> None:
    call(live.port, "GET", "/version")
    assert capsys.readouterr().err == ""


def test_every_route_answers_under_a_second_with_400_tasks(live: Live) -> None:
    card = live.backend.board_data["tasks"][0]
    live.backend.board_data["tasks"] = [{**card, "id": f"{i:08d}"} for i in range(400)]
    live.backend.usage_data["cost"]["per_task"] = [
        {"id": f"{i:08d}", "title": "t", "cost_usd": 0.1} for i in range(400)
    ]
    paths = ["/", "/version", "/api/board", f"/api/task/{live.backend.task_id}", "/api/usage"]
    for path in paths:
        started = time.perf_counter()
        assert call(live.port, "GET", path).status == 200
        assert time.perf_counter() - started < 1.0, path
    started = time.perf_counter()
    assert post(live, "ship").status == 200
    assert time.perf_counter() - started < 1.0


def test_concurrent_requests_all_succeed(live: Live) -> None:
    results: list[int] = []

    def hit() -> None:
        results.append(call(live.port, "GET", "/api/board").status)

    threads = [threading.Thread(target=hit) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(10)
    assert results == [200] * 16


def test_unknown_error_code_from_backend_is_internal(live: Live) -> None:
    live.backend.failure = BackendError("weird", "boom")
    assert call(live.port, "GET", "/api/board").status == 500


def shot_path(live: Live, name: str) -> str:
    return f"/api/task/{live.backend.task_id}/shot/{name}"


def test_shot_serves_a_png(live: Live) -> None:
    live.backend.shots["home.png"] = b"\x89PNG-bytes"
    r = call(live.port, "GET", shot_path(live, "home.png"))
    assert r.status == 200
    assert r.body == b"\x89PNG-bytes"
    assert r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-cache"
    assert r.headers["x-content-type-options"] == "nosniff"


@pytest.mark.parametrize(
    "name",
    ["missing.png", "a.jpg", "a.png.txt", "..%2F..%2Fstate.json", "%2e%2e%2fx.png", "a%20b.png", ".png"],
)
def test_shot_refuses_bad_or_unknown_names(live: Live, name: str) -> None:
    r = call(live.port, "GET", shot_path(live, name))
    assert r.status == 404
    assert r.json()["error"]["code"] == "not_found"
    assert all(c[0] != "shot" or c[2] == "missing.png" for c in live.backend.calls)


def test_shot_of_an_unknown_task_or_bad_id(live: Live) -> None:
    assert call(live.port, "GET", "/api/task/zzzzzzzz-0/shot/a.png").status == 404
    assert call(live.port, "GET", "/api/task/short/shot/a.png").status == 400


def test_shot_backend_failure_is_500(live: Live) -> None:
    live.backend.failure = RuntimeError("x")
    assert call(live.port, "GET", shot_path(live, "a.png")).status == 500


def test_upstream_unavailable_maps_to_502(live: Live) -> None:
    live.backend.failure = BackendError("upstream_unavailable", "todo MCP: down")
    r = call(live.port, "GET", "/api/usage")
    assert r.status == 502
    validate("response", r.json())


def test_stale_board_with_a_banner_is_still_a_200(live: Live) -> None:
    live.backend.board_data["error"] = {"code": "upstream_unavailable", "message": "todo MCP: down"}
    r = call(live.port, "GET", "/api/board")
    assert r.status == 200
    validate("board", r.json())
