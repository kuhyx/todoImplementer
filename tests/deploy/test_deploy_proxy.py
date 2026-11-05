"""oauth2-proxy/run.sh and google_oauth_handoff.sh against stubbed docker/xclip."""

from __future__ import annotations

import http.server
import stat
import threading
from collections.abc import Iterator

import deploy_tools as dt
import pytest
from deploy_testkit import DEPLOY, Env, Stubber

CLIENT = "123.apps.googleusercontent.com"
REDIRECT = "https://agents.kuhy.duckdns.org/oauth2/callback"

RUN = DEPLOY / "oauth2-proxy" / "run.sh"


def _creds(env: Env) -> None:
    dt.set_key(env.env_file, "OAUTH2_PROXY_CLIENT_ID", CLIENT)
    dt.set_key(env.env_file, "OAUTH2_PROXY_CLIENT_SECRET", "sec")


def test_proxy_dry_run_prints_pinned_command(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker")
    done = env.run("bash", str(RUN), "--dry-run")
    assert done.returncode == 0, done.stderr
    out = done.stdout
    for needle in (
        "quay.io/oauth2-proxy/oauth2-proxy:v7.15.5",
        "--provider=google",
        "--http-address=127.0.0.1:4186",
        f"--redirect-url={REDIRECT}",
        "--authenticated-emails-file=/etc/oauth2-proxy/emails.txt",
        "--network host",
        "credentials still missing",
    ):
        assert needle in out
    assert stat.S_IMODE(env.env_file.stat().st_mode) == 0o600
    emails = env.home / ".config" / "todoImplementer" / "oauth2-proxy-emails.txt"
    assert emails.read_text() == "krzysztofrudnicki0@gmail.com\n"
    assert "docker run" not in env.calls


def test_proxy_refuses_without_credentials(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker")
    stub("ss")
    done = env.run("bash", str(RUN))
    assert done.returncode == 1
    assert "missing" in done.stderr
    assert "docker run" not in env.calls


def test_proxy_starts_when_port_free(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker", 'case "$1" in ps) ;; esac')
    stub("ss")
    env.run("bash", str(RUN), "--dry-run")
    _creds(env)
    done = env.run("bash", str(RUN))
    assert done.returncode == 0, done.stderr
    assert "docker run -d --name todoimplementer-oauth2-proxy" in env.calls
    assert "rm -f todoimplementer-oauth2-proxy" in env.calls


def test_proxy_refuses_foreign_port_owner(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker")
    stub("ss", "echo 'LISTEN 127.0.0.1:4186 users:((other))'")
    env.run("bash", str(RUN), "--dry-run")
    _creds(env)
    done = env.run("bash", str(RUN))
    assert done.returncode == 1
    assert "is taken" in done.stderr
    assert "docker run" not in env.calls


def test_proxy_replaces_own_container(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker", 'case "$1" in ps) echo abc123;; esac')
    stub("ss", "echo 'LISTEN 127.0.0.1:4186'")
    env.run("bash", str(RUN), "--dry-run")
    _creds(env)
    assert env.run("bash", str(RUN)).returncode == 0
    assert "docker run -d" in env.calls


def test_proxy_usage(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("docker")
    assert env.run("bash", str(RUN), "--what").returncode == 1


HANDOFF = DEPLOY / "google_oauth_handoff.sh"


def test_handoff_guided_flow(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("xdg-open")
    stub("xclip", 'echo "CLIP:$(cat)" >> "$STUB_LOG"')
    done = env.run("bash", str(HANDOFF), stdin=f"\n\n\n{CLIENT}\nshh\n")
    assert done.returncode == 0, done.stderr
    clips = [c for c in env.calls.splitlines() if c.startswith("CLIP:")]
    assert clips == [
        "CLIP:todoImplementer",
        "CLIP:https://agents.kuhy.duckdns.org",
        f"CLIP:{REDIRECT}",
    ]
    assert "xdg-open https://console.cloud.google.com/apis/credentials/oauthclient" in env.calls
    saved = env.env_file.read_text()
    assert f"OAUTH2_PROXY_CLIENT_ID={CLIENT}" in saved
    assert "OAUTH2_PROXY_CLIENT_SECRET=shh" in saved
    assert stat.S_IMODE(env.env_file.stat().st_mode) == 0o600
    assert "shh" not in done.stdout


def test_handoff_prints_url_when_xdg_open_fails(box: tuple[Env, Stubber]) -> None:
    env, stub = box
    stub("xdg-open", "exit 3")
    stub("xclip")
    done = env.run("bash", str(HANDOFF), stdin=f"\n\n\n{CLIENT}\nshh\n")
    assert done.returncode == 0
    assert "open manually" in done.stdout


class _Proxy(http.server.BaseHTTPRequestHandler):
    location = ""

    def do_GET(self) -> None:
        """Answer every GET with the configured redirect."""
        self.send_response(302)
        self.send_header("Location", self.location)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        """Silence request logging."""
        del format, args


@pytest.fixture
def fake_proxy() -> Iterator[tuple[int, type[_Proxy]]]:
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _Proxy)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield httpd.server_port, _Proxy
    httpd.shutdown()
    httpd.server_close()


def test_handoff_verify_only(box: tuple[Env, Stubber], fake_proxy: tuple[int, type[_Proxy]]) -> None:
    env, _ = box
    port, handler = fake_proxy
    env.run("bash", str(DEPLOY / "oauth2-proxy" / "run.sh"), "--dry-run", PATH=env.env["PATH"])  # ensure-env
    _creds(env)
    handler.location = f"https://accounts.google.com/o/oauth2/auth?client_id={CLIENT}&redirect_uri={REDIRECT}"
    ok = env.run("bash", str(HANDOFF), "--verify-only", TODOIMPL_PROXY_PORT=str(port))
    assert ok.returncode == 0, ok.stderr
    assert "verified" in ok.stdout
    handler.location = "https://evil.example/"
    bad = env.run("bash", str(HANDOFF), "--verify-only", TODOIMPL_PROXY_PORT=str(port))
    assert bad.returncode == 1
    assert "evil.example" in bad.stderr


def test_handoff_verify_needs_credentials_and_usage(box: tuple[Env, Stubber]) -> None:
    env, _ = box
    assert env.run("bash", str(HANDOFF), "--verify-only").returncode == 1
    assert env.run("bash", str(HANDOFF), "--zzz").returncode == 1


def test_handoff_public_flag_targets_caddy_host(box: tuple[Env, Stubber]) -> None:
    env, _ = box
    env.run("bash", str(DEPLOY / "oauth2-proxy" / "run.sh"), "--dry-run")
    _creds(env)
    # Unreachable public host in the sandbox: the error must name the public URL.
    done = env.run("bash", str(HANDOFF), "--verify-only", "--public", HTTPS_PROXY="http://127.0.0.1:9")
    assert done.returncode == 1
    assert "agents.kuhy.duckdns.org" in done.stderr
