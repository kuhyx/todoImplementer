"""The /api/tokens mount: status passthrough, no store, crashes and prefix boundaries."""

from http import HTTPStatus
from pathlib import Path

import pytest
from httpfakes import Live, call
from todoimpl.tokens_api import paths, router


@pytest.fixture(autouse=True)
def _hermetic_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Never let a request reach the real token store."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path / "root"))
    monkeypatch.setenv("HOME", "/home/tester")


def test_tokens_without_a_store_is_503_with_its_own_body(live: Live) -> None:
    r = call(live.port, "GET", "/api/tokens/panel/overview?window=7d")
    assert r.status == 503
    assert "no token store" in r.json()["error"]
    assert r.headers["cache-control"] == "no-store"


def test_tokens_status_and_body_pass_through(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[tuple[str, str]] = []

    def fake(path: str, query: str) -> tuple[HTTPStatus, dict[str, object]]:
        seen.append((path, query))
        return HTTPStatus.OK, {"panels": []}

    monkeypatch.setattr(router, "handle", fake)
    for path in ("/api/tokens", "/api/tokens/session/abc"):
        r = call(live.port, "GET", f"{path}?cwd=x")
        assert (r.status, r.json()) == (200, {"panels": []})
    assert seen == [("/api/tokens", "cwd=x"), ("/api/tokens/session/abc", "cwd=x")]


def test_tokens_crash_is_a_contract_500(live: Live, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(path: str, query: str) -> tuple[HTTPStatus, dict[str, object]]:
        raise RuntimeError("secret detail")

    monkeypatch.setattr(router, "handle", boom)
    r = call(live.port, "GET", "/api/tokens")
    assert r.status == 500
    assert r.json()["error"]["code"] == "internal"
    assert "secret" not in r.body.decode()


def test_prefix_lookalike_is_not_mounted(live: Live) -> None:
    assert call(live.port, "GET", "/api/tokensfoo").status == 404
