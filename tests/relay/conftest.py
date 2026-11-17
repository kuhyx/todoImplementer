"""A fake RTDB holding todoimpl/v1-e2e (rtdb_relay's fake, re-rooted) and a Router over FakeBackend."""

import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from crdt_sync import E2eCipher
from rtdb_relay.seal import Sealer
from rtdb_relay.tests import _fake_rtdb
from rtdb_relay.tests._fake_rtdb import TEST_KEY, FakeRtdb
from todoimpl.http.app import make_server
from todoimpl.http.routes import Router
from todoimpl.relay.layout import LAYOUT

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "http"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from httpfakes import FakeBackend
from relayfakes import SessionRunner

ROOT = LAYOUT.root


@pytest.fixture(autouse=True)
def _todoimpl_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the package's fake at this app's root and layout."""
    monkeypatch.setattr(_fake_rtdb, "ROOT", ROOT)
    monkeypatch.setattr(_fake_rtdb, "TUTOR", LAYOUT)
    monkeypatch.setattr(_fake_rtdb, "sealer", lambda: Sealer(E2eCipher(TEST_KEY), LAYOUT))


@pytest.fixture(autouse=True)
def _scratch_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Sessions and token pages read ~/.claude and the run root: both empty scratch dirs here."""
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "run"))


@pytest.fixture
def fake() -> FakeRtdb:
    return FakeRtdb(now_ms=int(time.time() * 1000))


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()


@pytest.fixture
def router(backend: FakeBackend, tmp_path: Path) -> Iterator[Router]:
    server = make_server(backend, port=0, dist=tmp_path, build="b1")
    server.router.sessions_runner = SessionRunner()
    yield server.router
    server.server_close()
