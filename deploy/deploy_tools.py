"""Small, testable helpers behind the deploy shell scripts (no inline Python in shell).

Subcommands (all exit 0 on success, non-zero with a message on stderr):
  version-match EXPECTED          stdin = body of GET /version
  ensure-env FILE                 create the 0600 oauth2-proxy env file (idempotent)
  set-key FILE KEY                stdin = value; set KEY in FILE, keep mode 0600
  check-creds FILE                fail unless client id/secret are filled in
  write-emails FILE EMAIL         allow-list file with exactly one address
  check-start URL CLIENT_ID REDIRECT_URI
                                  /oauth2/start must 302 to accounts.google.com
"""  # noqa: INP001 - standalone script dir, not a package

from __future__ import annotations

import http.client
import json
import os
import secrets
import sys
import urllib.parse
from pathlib import Path
from typing import NoReturn

CLIENT_ID_VAR = "OAUTH2_PROXY_CLIENT_ID"
CLIENT_SECRET_VAR = "OAUTH2_PROXY_CLIENT_SECRET"  # noqa: S105 - env var name, not a secret
COOKIE_VAR = "OAUTH2_PROXY_COOKIE_SECRET"
VERSION_FIELDS = ("build", "build_id", "version", "hash", "commit")
GOOGLE_HOST = "accounts.google.com"


class DeployError(Exception):
    """A deploy precondition failed; the message is shown to the user as is."""


def _fail(message: str, cause: BaseException | None = None) -> NoReturn:
    """Raise DeployError(message), chained to cause when given."""
    raise DeployError(message) from cause


def parse_version(body: str) -> str:
    """Extract the build id from a /version body (plain text or a JSON object)."""
    text = body.strip()
    if not text.startswith("{"):
        return text
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        _fail(f"/version is not valid JSON: {exc}", exc)
    for key in VERSION_FIELDS:
        value = data.get(key)
        if isinstance(value, str) and value:
            return value
    _fail(f"/version has none of {VERSION_FIELDS}: {text[:80]}")


def version_match(expected: str, body: str) -> str:
    """Return the live build id; raise unless it equals the expected short hash."""
    live = parse_version(body)
    if live != expected:
        _fail(f"live build {live!r} != expected {expected!r}")
    return live


def read_env(path: Path) -> dict[str, str]:
    """Parse KEY=VALUE lines; blank lines and # comments are skipped."""
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            values[key.strip()] = value.strip()
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    """Write the env file atomically with mode 0600 (secrets never world-readable)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write("".join(f"{key}={value}\n" for key, value in values.items()))
    tmp.replace(path)


def ensure_env(path: Path) -> bool:
    """Create the env file with a fresh cookie secret; keep existing values. True if created."""
    values = read_env(path) if path.exists() else {}
    created = not values.get(COOKIE_VAR)
    values.setdefault(CLIENT_ID_VAR, "")
    values.setdefault(CLIENT_SECRET_VAR, "")
    if created:
        values[COOKIE_VAR] = secrets.token_hex(16)  # 32 ASCII bytes = AES-256 key
    write_env(path, values)
    return created


def set_key(path: Path, key: str, value: str) -> None:
    """Set one key (value without surrounding whitespace) and keep the other keys."""
    cleaned = value.strip()
    if not cleaned or "\n" in cleaned:
        _fail(f"refusing empty or multi-line value for {key}")
    values = read_env(path) if path.exists() else {}
    values[key] = cleaned
    write_env(path, values)


def check_creds(path: Path) -> None:
    """Fail closed: the proxy must not start without a Google client id and secret."""
    values = read_env(path) if path.exists() else {}
    missing = [k for k in (CLIENT_ID_VAR, CLIENT_SECRET_VAR, COOKIE_VAR) if not values.get(k)]
    if missing:
        _fail(f"{path}: missing {', '.join(missing)} (run google_oauth_handoff.sh)")


def write_emails(path: Path, email: str) -> None:
    """Write the one-address allow-list for --authenticated-emails-file."""
    if "@" not in email or any(c.isspace() for c in email):
        _fail(f"not an email address: {email!r}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(email.lower() + "\n", encoding="utf-8")


def fetch_redirect(url: str) -> tuple[int, str]:
    """GET url without following redirects; return (status, Location header or '')."""
    parts = urllib.parse.urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    conn = conn_cls(parts.netloc, timeout=10)
    try:
        conn.request("GET", path or "/")
        resp = conn.getresponse()
        return resp.status, resp.getheader("Location", "")
    except (http.client.HTTPException, OSError) as exc:
        _fail(f"cannot reach {url}: {exc}", exc)
    finally:
        conn.close()


def check_start(url: str, client_id: str, redirect_uri: str) -> str:
    """Prove /oauth2/start redirects to Google with our client id and redirect URI."""
    status, location = fetch_redirect(url)
    if status not in (301, 302, 303):
        _fail(f"{url} answered {status}, expected a redirect")
    parts = urllib.parse.urlsplit(location)
    query = urllib.parse.parse_qs(parts.query)
    if parts.hostname != GOOGLE_HOST:
        _fail(f"redirect goes to {parts.hostname!r}, not {GOOGLE_HOST}")
    if query.get("client_id") != [client_id]:
        _fail("redirect carries a different client_id than the env file")
    if query.get("redirect_uri") != [redirect_uri]:
        _fail(f"redirect_uri is {query.get('redirect_uri')}, want {redirect_uri}")
    return location


def main(argv: list[str], stdin: str | None = None) -> int:
    """CLI entry; returns the process exit code."""
    try:
        return _dispatch(argv, stdin)
    except (DeployError, IndexError, OSError) as exc:
        print(f"deploy_tools: {exc}", file=sys.stderr)
        return 1


def _dispatch(argv: list[str], stdin: str | None) -> int:
    cmd, args = argv[0], argv[1:]
    if cmd == "version-match":
        print(version_match(args[0], sys.stdin.read() if stdin is None else stdin))
    elif cmd == "ensure-env":
        print("created" if ensure_env(Path(args[0])) else "kept")
    elif cmd == "set-key":
        set_key(Path(args[0]), args[1], sys.stdin.read() if stdin is None else stdin)
    elif cmd == "check-creds":
        check_creds(Path(args[0]))
    elif cmd == "write-emails":
        write_emails(Path(args[0]), args[1])
    elif cmd == "check-start":
        print(check_start(args[0], args[1], args[2]))
    else:
        _fail(f"unknown command {cmd!r}")
    return 0


if __name__ == "__main__":  # pragma: no cover - thin wrapper
    sys.exit(main(sys.argv[1:]))
