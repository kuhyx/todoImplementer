"""The ready credits root of the pacing tests."""

from __future__ import annotations

import sys
from datetime import date
from typing import TYPE_CHECKING

import pytest
from todoimpl.apikey import cache
from todoimpl.apikey.keystatus import KeyStatus
from todoimpl.credits import ledger, live, setting

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Return a root: no plan limit, usable key, SDK python, $200 a month from the 1st, empty ledger."""
    ledger.reset()
    live.reset()
    key = tmp_path / "key"
    key.write_text("sk-ant-api03-" + "x" * 30)
    monkeypatch.setenv("TODOIMPL_APIKEY", str(key))
    monkeypatch.setenv("TODOIMPL_SDK_PYTHON", sys.executable)
    cache.put(KeyStatus("ok", date(2026, 12, 1), "fine"))
    path = setting.settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"credits_monthly_usd": 200, "credits_month_start_day": 1, "credits_cost_factor": 1}')
    return tmp_path
