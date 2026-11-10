"""The read-only plan usage probe (the endpoint Claude Code's /usage reads) and its stored copy."""

from __future__ import annotations

import json
import urllib.request
from typing import TYPE_CHECKING, Any, Self

import pytest
from todoimpl.usage import oauth

if TYPE_CHECKING:
    from pathlib import Path

NOW = 1_794_320_000.0
BODY = {
    "five_hour": None,
    "seven_day": {"utilization": 4.0, "resets_at": "2026-11-13T09:00:00.371530+00:00"},
}


def _creds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, expires: float = NOW + 3600) -> None:
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    data = {"claudeAiOauth": {"accessToken": "tok-secret", "expiresAt": int(expires * 1000)}}
    (tmp_path / ".credentials.json").write_text(json.dumps(data), encoding="utf-8")


def test_parse_turns_percent_into_fractions_and_iso_into_epoch() -> None:
    probe = oauth.parse(BODY, NOW)
    assert probe is not None
    assert probe.five_hour is None
    assert probe.seven_day == oauth.Window(0.04, 1794560400.371530)
    assert probe.blocked_until(NOW) is None


def test_parse_skips_malformed_windows_and_rejects_non_objects() -> None:
    assert oauth.parse([], NOW) is None
    odd = {"five_hour": {"utilization": "x", "resets_at": "2026-11-13T09:00:00+00:00"}, "seven_day": 3}
    bad_date = {"five_hour": {"utilization": 1.0, "resets_at": "soon"}, "seven_day": {"utilization": 1.0}}
    for body in (odd, bad_date):
        probe = oauth.parse(body, NOW)
        assert probe is not None
        assert (probe.five_hour, probe.seven_day) == (None, None)


def test_blocked_until_is_the_latest_reset_of_a_full_window() -> None:
    probe = oauth.Probe(NOW, oauth.Window(1.0, NOW + 100), oauth.Window(1.0, NOW + 900))
    assert probe.blocked_until(NOW) == NOW + 900
    assert probe.blocked_until(NOW + 950) is None
    assert oauth.Probe(NOW, oauth.Window(0.99, NOW + 100), None).blocked_until(NOW) is None


def test_store_round_trip_and_garbage(tmp_path: Path) -> None:
    probe = oauth.Probe(NOW, None, oauth.Window(0.04, NOW + 5))
    assert oauth.load(tmp_path) is None
    oauth.save(tmp_path, probe)
    assert oauth.load(tmp_path) == probe
    (tmp_path / oauth.FILE).write_text("[1]", encoding="utf-8")
    assert oauth.load(tmp_path) is None
    (tmp_path / oauth.FILE).write_text('{"at": "x"}', encoding="utf-8")
    assert oauth.load(tmp_path) is None
    (tmp_path / oauth.FILE).write_text("{", encoding="utf-8")
    assert oauth.load(tmp_path) is None
    (tmp_path / oauth.FILE).write_text('{"at": 1, "five_hour": {"utilization": "x"}}', encoding="utf-8")
    assert oauth.load(tmp_path) == oauth.Probe(1.0, None, None)


def test_fetch_sends_the_bearer_token_and_never_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _creds(tmp_path, monkeypatch)
    seen: dict[str, Any] = {}

    def get(url: str, headers: dict[str, str], timeout: float) -> object:
        seen.update(url=url, headers=headers, timeout=timeout)
        return BODY

    probe = oauth.fetch(NOW, get)
    assert probe is not None
    assert probe.at == NOW
    assert seen["url"] == oauth.URL
    assert seen["headers"]["Authorization"] == "Bearer tok-secret"

    def boom(url: str, headers: dict[str, str], timeout: float) -> object:
        raise OSError(url, headers, timeout)

    assert oauth.fetch(NOW, boom) is None


def test_fetch_is_unknown_without_a_usable_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def never(url: str, headers: dict[str, str], timeout: float) -> object:
        raise AssertionError(url, headers, timeout)

    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path))
    assert oauth.fetch(NOW, never) is None  # no file
    _creds(tmp_path, monkeypatch, expires=NOW - 1)
    assert oauth.fetch(NOW, never) is None  # expired
    (tmp_path / ".credentials.json").write_text('{"claudeAiOauth": {"accessToken": 5}}', encoding="utf-8")
    assert oauth.fetch(NOW, never) is None
    (tmp_path / ".credentials.json").write_text("[]", encoding="utf-8")
    assert oauth.fetch(NOW, never) is None


def test_default_getter_reads_json_over_http(monkeypatch: pytest.MonkeyPatch) -> None:
    class Reply:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(BODY).encode()

    seen: list[urllib.request.Request] = []

    def urlopen(request: urllib.request.Request, timeout: float) -> Reply:
        seen.append(request)
        assert timeout == oauth.TIMEOUT
        return Reply()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    assert oauth.http_get("https://example.test/u", {"X-A": "b"}, oauth.TIMEOUT) == BODY
    assert seen[0].full_url == "https://example.test/u"
    assert seen[0].get_header("X-a") == "b"
