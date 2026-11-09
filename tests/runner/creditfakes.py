"""Helpers for credit-route tests: a fake key, the fake SDK on the path, a usable key status."""

from __future__ import annotations

import os
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from todoimpl.apikey import cache
from todoimpl.apikey.keystatus import KeyStatus

if TYPE_CHECKING:
    import pytest

SHIMS = Path(__file__).resolve().parents[1] / "shims"
FAKE_KEY = "sk-ant-api03-" + "f" * 30  # not a real key; tests never reach the network


def key_file() -> Path:
    """Return the key path the autouse fixture points at (an empty temp dir)."""
    return Path(os.environ["TODOIMPL_APIKEY"])


def enable_credits(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give a usable key, the fake `claude_agent_sdk` (tests/shims) run by this interpreter, an ok status."""
    key_file().write_text(FAKE_KEY + "\n", encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_SDK_PYTHON", sys.executable)
    monkeypatch.setenv("PYTHONPATH", str(SHIMS))
    cache.put(KeyStatus("ok", date(2099, 1, 1), "fine"))
