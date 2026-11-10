"""GET /api/task/<id>/issues serves the raw free-issues.jsonl."""

from httpfakes import Live, call


def test_issues_serve_the_raw_log_as_ndjson(live: Live) -> None:
    live.backend.issues_text = '{"child": "kuhyx/a"}\n'
    r = call(live.port, "GET", f"/api/task/{live.backend.task_id}/issues")
    assert r.status == 200
    assert r.headers["content-type"].startswith("application/x-ndjson")
    assert r.body == b'{"child": "kuhyx/a"}\n'
    assert r.headers["cache-control"] == "no-store"


def test_issues_of_an_unknown_task_or_a_bad_id_are_errors(live: Live) -> None:
    assert call(live.port, "GET", "/api/task/ffffffff-0/issues").status == 404
    bad = call(live.port, "GET", "/api/task/nope/issues")
    assert bad.status == 400
    assert bad.json()["error"]["code"] == "bad_request"
