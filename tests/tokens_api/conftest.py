"""Hermetic roots for the tokens_api tests: temp HOME and filesystem root, never the real store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
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
