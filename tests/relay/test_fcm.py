"""The FCM v1 sender: key file, RS256 assertion, cached access token, data-only send, error mapping."""

import asyncio
import base64
import json
import runpy
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, padding, rsa
from todoimpl.relay import fcm, fcm_check
from todoimpl.relay.fcm import Account, BadKeyError, FcmError, Sender, UnregisteredError

PRIVATE = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PEM = PRIVATE.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
EC_PEM = (
    ec.generate_private_key(ec.SECP256R1())
    .private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
    )
    .decode()
)
INFO = {
    "type": "service_account",
    "project_id": "proj",
    "client_email": "sender@proj.iam.gserviceaccount.com",
    "private_key": PEM,
    "token_uri": "https://oauth2.example/token",
}


def b64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def write_key(tmp_path: Path, info: Any = INFO) -> Path:
    path = tmp_path / "key.json"
    path.write_text(json.dumps(info) if not isinstance(info, str) else info, encoding="utf-8")
    return path


def test_default_key_path_is_under_the_apps_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert fcm.key_path() == tmp_path / ".config" / "todoImplementer" / "fcm-service-account.json"


@pytest.mark.parametrize(
    ("info", "says"),
    [
        (None, "no Firebase service-account key"),
        ("{not json", "unreadable Firebase service-account key"),
        ({**INFO, "private_key": None}, "incomplete Firebase service-account key"),
        ([1], "incomplete Firebase service-account key"),
        (
            {**INFO, "private_key": "-----BEGIN PRIVATE KEY-----\nAAAA\n-----END PRIVATE KEY-----\n"},
            "bad private key",
        ),
        ({**INFO, "private_key": EC_PEM}, "not RSA"),
    ],
)
def test_a_bad_key_file_names_the_problem(tmp_path: Path, info: Any, says: str) -> None:
    path = tmp_path / "missing.json" if info is None else write_key(tmp_path, info)
    with pytest.raises(BadKeyError, match=says):
        Account.load(path)


def test_assertion_is_rs256_signed_for_the_messaging_scope(tmp_path: Path) -> None:
    account = Account.load(write_key(tmp_path))
    header, claims, signature = account.assertion(1_000).split(".")
    assert json.loads(b64(header)) == {"alg": "RS256", "typ": "JWT"}
    assert json.loads(b64(claims)) == {
        "iss": INFO["client_email"],
        "scope": fcm.SCOPE,
        "aud": INFO["token_uri"],
        "iat": 1_000,
        "exp": 1_000 + 3600,
    }
    PRIVATE.public_key().verify(
        b64(signature), f"{header}.{claims}".encode(), padding.PKCS1v15(), hashes.SHA256()
    )


class Google:
    """Token endpoint and FCM endpoint behind one MockTransport."""

    def __init__(self) -> None:
        self.tokens = 0
        self.sent: list[dict[str, Any]] = []
        self.token_status = 200
        self.send_status = 200
        self.send_body: dict[str, Any] | bytes = {"name": "projects/proj/messages/1"}

    def handle(self, request: httpx.Request) -> httpx.Response:
        if request.url == INFO["token_uri"]:
            self.tokens += 1
            form = dict(x.split("=", 1) for x in request.content.decode().split("&"))
            assert form["grant_type"] == "urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer"
            body = {"access_token": f"at{self.tokens}", "expires_in": 3599}
            return httpx.Response(
                self.token_status, json=body if self.token_status == 200 else {"error": "x"}
            )
        assert str(request.url) == "https://fcm.googleapis.com/v1/projects/proj/messages:send"
        assert request.headers["authorization"] == f"Bearer at{self.tokens}"
        self.sent.append(json.loads(request.content))
        if isinstance(self.send_body, bytes):
            return httpx.Response(self.send_status, content=self.send_body)
        return httpx.Response(self.send_status, json=self.send_body)


def sender(tmp_path: Path, google: Google, now: list[float]) -> Sender:
    http = httpx.AsyncClient(transport=httpx.MockTransport(google.handle))
    return Sender(http, path=write_key(tmp_path), clock=lambda: now[0])


def test_send_is_data_only_high_priority_and_reuses_the_token(tmp_path: Path) -> None:
    google, now = Google(), [1_000.0]
    out = sender(tmp_path, google, now)

    async def go() -> None:
        await out.send("tok-a", {"v": "1"})
        now[0] += 3000  # still more than a minute left on the hour-long token
        await out.send("tok-b", {"v": "1"})
        now[0] += 600  # inside the last minute: a fresh token
        await out.send("tok-c", {"v": "1"})

    asyncio.run(go())
    assert google.tokens == 2
    assert google.sent[0] == {
        "message": {"token": "tok-a", "data": {"v": "1"}, "android": {"priority": "high"}}
    }
    assert [m["message"]["token"] for m in google.sent] == ["tok-a", "tok-b", "tok-c"]


def test_token_endpoint_failure_is_an_fcm_error(tmp_path: Path) -> None:
    google = Google()
    google.token_status = 400
    with pytest.raises(FcmError, match="token endpoint said 400"):
        asyncio.run(sender(tmp_path, google, [1.0]).send("tok", {}))


@pytest.mark.parametrize(
    ("status", "body", "error"),
    [
        (404, {"error": {"status": "NOT_FOUND", "message": "gone"}}, UnregisteredError),
        (400, {"error": {"details": [{"errorCode": "UNREGISTERED"}], "message": "x"}}, UnregisteredError),
        (400, {"error": {"details": "odd", "message": "bad arg"}}, FcmError),
        (503, {"oops": 1}, FcmError),
        (502, b"<html/>", FcmError),  # a proxy's page, not JSON
    ],
)
def test_send_errors(
    tmp_path: Path, status: int, body: dict[str, Any] | bytes, error: type[Exception]
) -> None:
    google = Google()
    google.send_status, google.send_body = status, body
    with pytest.raises(error, match=f"FCM said {status}"):
        asyncio.run(sender(tmp_path, google, [1.0]).send("tok", {}))


def test_a_network_failure_is_an_fcm_error(tmp_path: Path) -> None:
    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(down))
    with pytest.raises(FcmError, match="cannot reach Google"):
        asyncio.run(Sender(http, path=write_key(tmp_path)).send("tok", {}))


def test_check_cli_trades_the_key_for_a_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    key = fcm.key_path()
    key.parent.mkdir(parents=True)
    key.write_text(json.dumps(INFO), encoding="utf-8")
    google = Google()
    assert fcm_check.main(httpx.MockTransport(google.handle)) == 0
    assert capsys.readouterr().out == "ok proj\n"
    assert (google.tokens, google.sent) == (1, [])


def test_check_cli_names_a_missing_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delitem(sys.modules, "todoimpl.relay.fcm_check")  # run it fresh, as `python -m` does
    with pytest.raises(SystemExit) as done:
        runpy.run_module("todoimpl.relay.fcm_check", run_name="__main__")
    assert done.value.code == 1
    assert capsys.readouterr().err.startswith("FAIL no Firebase service-account key at ")
