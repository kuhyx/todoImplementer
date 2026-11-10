"""A fake gateway on a free port, the two secret files in a temp dir, and nothing of kuhy's real ones."""

from __future__ import annotations

import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from gatewayfakes import API_KEY, NOW, PASSWORD, Gateway, world


@pytest.fixture
def secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Write the gateway secret files with the fake key and password."""
    where = tmp_path / "omniroute"
    where.mkdir()
    (where / "api_key").write_text(API_KEY + "\n", encoding="utf-8")
    (where / "admin_password").write_text(PASSWORD + "\n", encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_OMNIROUTE_DIR", str(where))
    return where


@pytest.fixture
def gateway(secrets: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Gateway]:
    """Start a fake gateway answering for the fixed NOW; the env points the client at it."""
    fake = Gateway(world(NOW))
    monkeypatch.setenv("TODOIMPL_FREE_GATEWAY", fake.url)
    yield fake
    fake.stop()
