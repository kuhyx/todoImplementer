"""Fixtures for the deploy tests: stubbed CLIs and a hermetic script runner."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from deploy_testkit import Env, Stubber


@pytest.fixture
def stub_bin(tmp_path: Path) -> tuple[Path, Stubber]:
    """Return a bin dir for PATH plus a function that writes a logging stub into it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    def stub(name: str, body: str = "") -> None:
        path = bin_dir / name
        path.write_text(f'#!/bin/bash\necho "{name} $*" >> "$STUB_LOG"\n{body}\n')
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return bin_dir, stub


@pytest.fixture
def box(tmp_path: Path, stub_bin: tuple[Path, Stubber]) -> tuple[Env, Stubber]:
    """Return a runner Env plus the stub writer sharing one bin dir."""
    return Env(tmp_path, stub_bin[0]), stub_bin[1]
