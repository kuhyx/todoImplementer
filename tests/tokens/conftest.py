"""Keep every token-store test away from the real ``~/.claude`` and the real store."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from todoimpl.tokens import ab, aux, context_files, ingest, schema
from todoimpl.tokens.audit import history

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def _isolated_sources(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Point every aux source at an empty tmp directory."""
    claude = tmp_path / "claude-home"
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv(schema.ENV_DB, str(tmp_path / "env-db" / "tokens.sqlite"))
    monkeypatch.setattr(schema, "DEFAULT_DB", tmp_path / "default-db" / "tokens.sqlite")
    monkeypatch.setattr(ingest, "ROOT", claude / "projects")
    monkeypatch.setattr(history, "REPORT_DIR", claude / "token-report")
    monkeypatch.setattr(aux, "AUTOPSY", claude / "autopsy.jsonl")
    monkeypatch.setattr(aux, "PROMPT_HISTORY", claude / "history.jsonl")
    monkeypatch.setattr(aux, "TIME_CAP", claude / "time-cap.jsonl")
    monkeypatch.setattr(ab, "LOG", claude / "agent-ab.jsonl")
    monkeypatch.setattr(ab, "BUILD_LOG", claude / "agent-ab-build.jsonl")
    monkeypatch.setattr(context_files, "CLAUDE_DIR", claude)
    monkeypatch.setattr(context_files, "SRC_DIR", claude / "src")
