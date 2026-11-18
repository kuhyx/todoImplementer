"""Hermetic roots for the sessions tests: temp HOME and filesystem root, never the real ~/.claude."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.sessions import api, origin
from todoimpl.tokens_api import paths

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def sysroot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point every filesystem read at a disposable tree (HOME=/home/tester under it)."""
    monkeypatch.setenv(paths.ROOT_ENV, str(tmp_path))
    monkeypatch.setenv("HOME", "/home/tester")
    (tmp_path / "home/tester").mkdir(parents=True)
    return tmp_path


@pytest.fixture(autouse=True)
def fresh_scanner(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each test a fresh scanner cache, so one test's transcripts never leak into the next."""
    monkeypatch.setattr(api, "SCANNER", api.Scanner())


@pytest.fixture(autouse=True)
def fresh_origins(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give each test a fresh cwd -> repo cache, so one test's git answers never leak into the next."""
    monkeypatch.setattr(origin, "CACHE", origin.OriginCache())
