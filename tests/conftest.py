"""Every test launches turn hosts directly: no test may call the real systemd-run."""

import pytest


@pytest.fixture(autouse=True)
def _direct_turn_launch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TODOIMPL_TURN_LAUNCH", "direct")
