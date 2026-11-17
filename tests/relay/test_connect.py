"""Where the relay signs in: crdt-sync's config, this app's session, the passphrase, a stable id."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from crdt_sync import ConfigError, FirebaseAuthError
from rtdb_relay.rtdb import RtdbError
from todoimpl.relay import connect


class Config:
    api_key = "k"
    database_url = "https://db.test"

    @staticmethod
    def load() -> Config:
        return Config()


class Provider:
    session = True

    def __init__(self, api_key: str, store: Any) -> None:
        self.store = store

    def has_session(self) -> bool:
        return self.session

    def id_token(self) -> str:
        if not self.session:
            raise FirebaseAuthError("revoked")
        return "tok"


def test_connect_needs_the_config(monkeypatch: pytest.MonkeyPatch) -> None:
    class NoConfig:
        @staticmethod
        def load() -> None:
            raise ConfigError("missing firebase.json")

    monkeypatch.setattr(connect, "FirebaseConfig", NoConfig)
    with pytest.raises(connect.RelaySetupError, match="firebase config"):
        connect.connect()


def test_connect_needs_this_apps_session(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connect, "FirebaseConfig", Config)
    monkeypatch.setattr(connect, "FirebaseTokenProvider", Provider)
    monkeypatch.setattr(Provider, "session", False)
    with pytest.raises(connect.RelaySetupError, match=r"todoImplementer/firebase_auth\.json"):
        connect.connect()


def test_connect_with_a_session_signs_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(connect, "FirebaseConfig", Config)
    monkeypatch.setattr(connect, "FirebaseTokenProvider", Provider)
    endpoint = connect.connect()
    assert endpoint.database_url == "https://db.test"
    assert asyncio.run(endpoint.token()) == "tok"
    client = endpoint.client("todoimpl/v1-e2e")
    assert client.root == "todoimpl/v1-e2e"
    asyncio.run(client.aclose())


def test_a_revoked_session_is_an_rtdb_error() -> None:
    provider = Provider("k", None)
    provider.session = False
    with pytest.raises(RtdbError, match="revoked"):
        asyncio.run(connect.token_source(provider)())


def test_passphrase(tmp_path: Path) -> None:
    with pytest.raises(connect.RelaySetupError, match="no crdt-sync password"):
        connect.passphrase(tmp_path / "password")
    (tmp_path / "password").write_text("\n", encoding="utf-8")
    with pytest.raises(connect.RelaySetupError, match="empty"):
        connect.passphrase(tmp_path / "password")
    (tmp_path / "password").write_text("s3cret\n", encoding="utf-8")
    assert connect.passphrase(tmp_path / "password") == "s3cret"


def test_passphrase_default_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    with pytest.raises(connect.RelaySetupError):
        connect.passphrase()


def test_worker_id_is_stable(tmp_path: Path) -> None:
    first = connect.device_id(tmp_path)
    assert first == connect.device_id(tmp_path)
    assert len(first) == 36
