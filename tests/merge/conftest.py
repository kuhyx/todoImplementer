"""Hermetic fixtures for the merge tests: a fake todo MCP, a temp run root, a fake `claude` on PATH."""

import os
import stat
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "shims"))

from fake_todo_mcp import FakeTodoMcp  # noqa: E402
from mergefakes import Rig, make_rig  # noqa: E402

FAKE_CLAUDE = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["FAKE_LOG"], "a") as log:
    log.write(json.dumps({"argv": sys.argv[1:], "stdin": sys.stdin.read(),
                          "auto": os.environ.get("CLAUDE_AUTO_CONTINUE")}) + "\\n")
sys.stdout.write(os.environ["FAKE_STDOUT"])
sys.exit(int(os.environ.get("FAKE_RC", "0")))
"""


@pytest.fixture
def fake() -> Iterator[FakeTodoMcp]:
    with FakeTodoMcp() as server:
        yield server


@pytest.fixture
def rig(fake: FakeTodoMcp, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Rig:
    monkeypatch.setenv("TODOIMPL_HOME", str(tmp_path / "run"))
    return make_rig(fake, tmp_path / "run")


@pytest.fixture
def shim(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Put a fake `claude` first on PATH; it logs argv and stdin to $FAKE_LOG and prints $FAKE_STDOUT."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    claude = bin_dir / "claude"
    claude.write_text(FAKE_CLAUDE)
    claude.chmod(claude.stat().st_mode | stat.S_IXUSR)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.delenv("TODOIMPL_CLAUDE", raising=False)
    monkeypatch.setenv("FAKE_LOG", str(tmp_path / "calls.log"))
    return tmp_path / "calls.log"
