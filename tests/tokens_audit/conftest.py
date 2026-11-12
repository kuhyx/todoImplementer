"""Keep every token_audit test away from the real ``~/.claude`` state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.tokens.audit import __main__ as cli
from todoimpl.tokens.audit import history, report, surfaces, unused

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point HOME and every module-level ``~/.claude`` constant at tmp_path."""
    home = tmp_path / "home"
    claude = home / ".claude"
    claude.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    # The audit cache lives under HOME unless one of these points elsewhere.
    monkeypatch.delenv("XDG_CACHE_HOME", raising=False)
    monkeypatch.delenv("TODOIMPL_HOME", raising=False)
    monkeypatch.setattr(history, "REPORT_DIR", claude / "token-report")
    monkeypatch.setattr(report, "REPORT_DIR", claude / "token-report")
    monkeypatch.setattr(cli, "TRANSCRIPT_ROOT", claude / "projects")
    monkeypatch.setattr(unused, "TRANSCRIPT_ROOT", claude / "projects")
    monkeypatch.setattr(surfaces, "CLAUDE_DIR", claude)
    monkeypatch.setattr(surfaces, "GLOBAL_CONFIG", home / ".claude.json")
    monkeypatch.setattr(surfaces, "SETTINGS", claude / "settings.json")
    return home
