"""GET /api/merges and POST /api/merge/<group>/<merge|dismiss>: gate, strict body, contract answers."""

from typing import Any

import pytest
from contract_lib import validate
from httpfakes import Live, call
from todoimpl.http.backend import BackendError

GROUP = "0123456789ab"
SUGGESTION = {
    "id": GROUP,
    "title": "Text-free",
    "reason": "same change",
    "members": [
        {"id": "aaaaaaaa-0", "title": "A", "repo": "kuhyx/a"},
        {"id": "bbbbbbbb-1", "title": "B", "repo": "kuhyx/b"},
    ],
    "actions": [
        {"id": "merge", "label": "Merge", "enabled": False, "reason": "aaaaaaaa-0 has a live run (plan)"},
        {"id": "dismiss", "label": "Dismiss", "enabled": True, "reason": None},
    ],
}


class FakeMerges:
    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []
        self.fail: BackendError | None = None

    def suggestions(self) -> dict[str, Any]:
        self.calls.append(("suggestions",))
        return {"suggestions": [SUGGESTION]}

    def _act(self, name: str, group: str) -> dict[str, Any]:
        self.calls.append((name, group))
        if self.fail is not None:
            raise self.fail
        return {"ok": True, "new_id": None if name == "dismiss" else "aaaaaaaa-3", "suggestions": []}

    def merge(self, group_id: str) -> dict[str, Any]:
        return self._act("merge", group_id)

    def dismiss(self, group_id: str) -> dict[str, Any]:
        return self._act("dismiss", group_id)


@pytest.fixture
def merges(live: Live) -> FakeMerges:
    fake = FakeMerges()
    live.backend.merge_service = fake  # type: ignore[attr-defined]
    return fake


def post(live: Live, path: str, body: Any = None, **hdr: str) -> Any:
    headers = {k: v for k, v in {**live.post_headers(), **hdr}.items() if v != "-"}
    return call(live.port, "POST", path, body, headers)


def test_get_answers_the_contract_shape(live: Live, merges: FakeMerges) -> None:
    r = call(live.port, "GET", "/api/merges")
    assert r.status == 200
    validate("merge", r.json())
    assert merges.calls == [("suggestions",)]


@pytest.mark.parametrize("action", ["merge", "dismiss"])
def test_post_runs_the_action_and_answers_the_contract(live: Live, merges: FakeMerges, action: str) -> None:
    r = post(live, f"/api/merge/{GROUP}/{action}", {})
    assert r.status == 200, r.body
    validate("merge", r.json(), "response")
    validate("merge", {}, action)
    assert merges.calls == [(action, GROUP)]


def test_post_without_a_body_is_fine(live: Live, merges: FakeMerges) -> None:
    assert post(live, f"/api/merge/{GROUP}/dismiss").status == 200


@pytest.mark.parametrize(
    "hdr",
    [
        {"Origin": "https://evil.example"},
        {"Origin": "-"},
        {"X-Todoimpl-Token": "wrong"},
        {"X-Todoimpl-Token": "-"},
    ],
)
def test_post_needs_origin_and_token(live: Live, merges: FakeMerges, hdr: dict[str, str]) -> None:
    r = post(live, f"/api/merge/{GROUP}/merge", {}, **hdr)
    assert r.status == 403
    validate("merge", r.json(), "response")
    assert merges.calls == []


@pytest.mark.parametrize("body", [{"x": 1}, "[]", "nope"])
def test_post_refuses_a_bad_body(live: Live, merges: FakeMerges, body: Any) -> None:
    r = post(live, f"/api/merge/{GROUP}/merge", body)
    assert r.status == 400
    assert merges.calls == []


@pytest.mark.parametrize(
    "path", ["/api/merge/short/merge", f"/api/merge/{GROUP}/other", f"/api/merge/{GROUP.upper()}/merge"]
)
def test_unknown_paths_are_404(live: Live, merges: FakeMerges, path: str) -> None:
    assert post(live, path, {}).status == 404


@pytest.mark.parametrize(
    ("code", "status"),
    [("disabled", 409), ("not_found", 404), ("conflict", 409), ("upstream_unavailable", 502)],
)
def test_refusals_keep_their_code(live: Live, merges: FakeMerges, code: str, status: int) -> None:
    merges.fail = BackendError(code, "why not")
    r = post(live, f"/api/merge/{GROUP}/merge", {})
    assert r.status == status
    validate("merge", r.json(), "response")
    assert r.json()["error"] == {"code": code, "message": "why not"}


def test_a_backend_without_merges_has_no_such_routes(live: Live) -> None:
    assert call(live.port, "GET", "/api/merges").status == 404
    assert post(live, f"/api/merge/{GROUP}/merge", {}).status == 404
