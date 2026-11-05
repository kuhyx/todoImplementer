"""The fake `claude` shim's script queue (tests/shims/claude)."""

from __future__ import annotations

import importlib.machinery
import json
from pathlib import Path
from types import ModuleType

import pytest

SHIM = Path(__file__).parent / "shims" / "claude"


def _load_shim() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("fake_claude_shim", str(SHIM))
    module = ModuleType(loader.name)
    loader.exec_module(module)
    return module


def test_t501_script_claimed_by_another_turn_is_skipped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A script another turn claimed between glob and claim is skipped, never read after it vanished."""
    shim = _load_shim()
    folder = tmp_path / "abcd1234"
    folder.mkdir()
    gone = folder / "000.jsonl"  # listed by glob, then renamed away by a concurrent turn
    mine = folder / "001.jsonl"
    mine.write_text(json.dumps({"_fake": "text", "text": "mine"}) + "\n", encoding="utf-8")
    monkeypatch.setattr(shim, "sorted", lambda _files: [gone, mine], raising=False)

    steps = shim.next_script(tmp_path, "abcd1234")

    assert steps == [{"_fake": "text", "text": "mine"}]
    assert not mine.exists()
    assert mine.with_suffix(".used").exists()
