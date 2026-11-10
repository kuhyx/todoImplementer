"""GET /api/umbrella/<id> serves the tracking view; .../log/<child> a worker log tail."""

from contract_lib import validate
from httpfakes import Live, call


def test_the_track_is_served_as_json_and_matches_the_contract(live: Live) -> None:
    r = call(live.port, "GET", f"/api/umbrella/{live.backend.task_id}")
    assert r.status == 200
    validate("track", r.json())
    assert ("umbrella", live.backend.task_id) in live.backend.calls


def test_an_unknown_umbrella_or_a_bad_id_is_an_error(live: Live) -> None:
    assert call(live.port, "GET", "/api/umbrella/ffffffff-0").status == 404
    bad = call(live.port, "GET", "/api/umbrella/nope")
    assert (bad.status, bad.json()["error"]["code"]) == (400, "bad_request")
    assert call(live.port, "GET", f"/api/umbrella/{live.backend.task_id}/log/nope").status == 400


def test_a_worker_log_is_plain_text_and_never_cached(live: Live) -> None:
    live.backend.log_text = "line one\nline two\n"
    tid = live.backend.task_id
    r = call(live.port, "GET", f"/api/umbrella/{tid}/log/{tid}")
    assert r.status == 200
    assert r.headers["content-type"].startswith("text/plain")
    assert r.headers["cache-control"] == "no-store"
    assert r.body == b"line one\nline two\n"


def test_a_missing_worker_log_is_not_found(live: Live) -> None:
    tid = live.backend.task_id
    assert call(live.port, "GET", f"/api/umbrella/{tid}/log/ffffffff-9").status == 404
