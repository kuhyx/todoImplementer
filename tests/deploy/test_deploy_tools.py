"""Unit tests for deploy/deploy_tools.py (100 % line + branch)."""

from __future__ import annotations

import http.server
import io
import json
import stat
import threading
from collections.abc import Iterator
from pathlib import Path

import deploy_tools as dt
import pytest

CLIENT = "123.apps.googleusercontent.com"
REDIRECT = "https://agents.kuhy.duckdns.org/oauth2/callback"


def test_parse_version_plain_and_json() -> None:
    assert dt.parse_version(" abc1234\n") == "abc1234"
    assert dt.parse_version('{"build": "abc1234"}') == "abc1234"
    assert dt.parse_version('{"build": "", "version": "v1"}') == "v1"


@pytest.mark.parametrize("body", ["{broken", '{"x": 1}', "{}"])
def test_parse_version_rejects_unusable_json(body: str) -> None:
    with pytest.raises(dt.DeployError):
        dt.parse_version(body)


def test_version_match() -> None:
    assert dt.version_match("abc", "abc\n") == "abc"
    with pytest.raises(dt.DeployError, match="!= expected"):
        dt.version_match("abc", "def")


def test_env_roundtrip_skips_comments(tmp_path: Path) -> None:
    path = tmp_path / "e.env"
    path.write_text("# c\n\nA=1\n  B = two \n")
    assert dt.read_env(path) == {"A": "1", "B": "two"}


def test_ensure_env_creates_0600_and_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "cfg" / "p.env"
    assert dt.ensure_env(path) is True
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    first = dt.read_env(path)
    assert len(first[dt.COOKIE_VAR]) == 32
    assert first[dt.CLIENT_ID_VAR] == ""
    assert dt.ensure_env(path) is False
    assert dt.read_env(path) == first


def test_set_key_keeps_others_and_mode(tmp_path: Path) -> None:
    path = tmp_path / "p.env"
    dt.set_key(path, dt.CLIENT_ID_VAR, f" {CLIENT}\n")
    dt.ensure_env(path)
    dt.set_key(path, dt.CLIENT_SECRET_VAR, "s3cret")
    values = dt.read_env(path)
    assert values[dt.CLIENT_ID_VAR] == CLIENT
    assert values[dt.CLIENT_SECRET_VAR] == "s3cret"
    assert dt.COOKIE_VAR in values
    assert stat.S_IMODE(path.stat().st_mode) == 0o600


@pytest.mark.parametrize("value", ["", "  \n", "a\nb"])
def test_set_key_rejects_bad_values(tmp_path: Path, value: str) -> None:
    with pytest.raises(dt.DeployError):
        dt.set_key(tmp_path / "p.env", "K", value)


def test_check_creds(tmp_path: Path) -> None:
    path = tmp_path / "p.env"
    with pytest.raises(dt.DeployError, match="missing"):
        dt.check_creds(path)
    dt.ensure_env(path)
    with pytest.raises(dt.DeployError, match=dt.CLIENT_ID_VAR):
        dt.check_creds(path)
    dt.set_key(path, dt.CLIENT_ID_VAR, CLIENT)
    dt.set_key(path, dt.CLIENT_SECRET_VAR, "x")
    dt.check_creds(path)


def test_write_emails(tmp_path: Path) -> None:
    path = tmp_path / "d" / "emails.txt"
    dt.write_emails(path, "A@B.com")
    assert path.read_text() == "a@b.com\n"
    for bad in ("nobody", "a b@c.d"):
        with pytest.raises(dt.DeployError):
            dt.write_emails(path, bad)


class _Handler(http.server.BaseHTTPRequestHandler):
    location = ""
    status = 302

    def do_GET(self) -> None:
        self.send_response(self.status)
        if self.location:
            self.send_header("Location", self.location)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence request logging."""
        del format, args


@pytest.fixture
def server() -> Iterator[tuple[str, type[_Handler]]]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    _Handler.location, _Handler.status = "", 302
    yield f"http://127.0.0.1:{httpd.server_port}/oauth2/start", _Handler
    httpd.shutdown()
    httpd.server_close()


def _google(client: str = CLIENT, redirect: str = REDIRECT, host: str = dt.GOOGLE_HOST) -> str:
    return f"https://{host}/o/oauth2/auth?client_id={client}&redirect_uri={redirect}"


def test_check_start_ok(server: tuple[str, type[_Handler]]) -> None:
    url, handler = server
    handler.location = _google()
    assert dt.check_start(url, CLIENT, REDIRECT) == handler.location


def test_check_start_failures(server: tuple[str, type[_Handler]]) -> None:
    url, handler = server
    handler.status = 200
    with pytest.raises(dt.DeployError, match="expected a redirect"):
        dt.check_start(url, CLIENT, REDIRECT)
    handler.status = 404
    with pytest.raises(dt.DeployError, match="404"):
        dt.check_start(url, CLIENT, REDIRECT)
    handler.status = 302
    for location, text in (
        (_google(host="evil.example"), "evil.example"),
        (_google(client="other"), "client_id"),
        (_google(redirect="https://x/cb"), "redirect_uri"),
    ):
        handler.location = location
        with pytest.raises(dt.DeployError, match=text):
            dt.check_start(url, CLIENT, REDIRECT)


def test_fetch_redirect_unreachable() -> None:
    with pytest.raises(dt.DeployError, match="cannot reach"):
        dt.fetch_redirect("http://127.0.0.1:9/")


def test_main_dispatch(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    env = tmp_path / "p.env"
    assert dt.main(["version-match", "abc"], stdin="abc\n") == 0
    assert dt.main(["ensure-env", str(env)]) == 0
    assert dt.main(["ensure-env", str(env)]) == 0
    assert dt.main(["set-key", str(env), dt.CLIENT_ID_VAR], stdin=CLIENT) == 0
    assert dt.main(["set-key", str(env), dt.CLIENT_SECRET_VAR], stdin="s") == 0
    assert dt.main(["check-creds", str(env)]) == 0
    assert dt.main(["write-emails", str(tmp_path / "e"), "a@b.c"]) == 0
    out = capsys.readouterr().out.split()
    assert out[:3] == ["abc", "created", "kept"]


def test_main_reads_stdin_when_not_injected(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("abc"))
    assert dt.main(["version-match", "abc"]) == 0
    monkeypatch.setattr("sys.stdin", io.StringIO("v"))
    assert dt.main(["set-key", str(tmp_path / "e"), "K"]) == 0


def test_main_check_start(server: tuple[str, type[_Handler]], capsys: pytest.CaptureFixture[str]) -> None:
    url, handler = server
    handler.location = _google()
    assert dt.main(["check-start", url, CLIENT, REDIRECT]) == 0
    assert "accounts.google.com" in capsys.readouterr().out


@pytest.mark.parametrize("argv", [[], ["nope"], ["version-match"], ["version-match", "a"]])
def test_main_errors_exit_1(argv: list[str], capsys: pytest.CaptureFixture[str]) -> None:
    assert dt.main(argv, stdin="zzz") == 1
    assert "deploy_tools:" in capsys.readouterr().err


def test_json_version_body_matches() -> None:
    assert dt.version_match("abc", json.dumps({"build": "abc"})) == "abc"
