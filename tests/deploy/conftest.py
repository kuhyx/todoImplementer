"""Fixtures for the deploy tests: stubbed CLIs and a hermetic script runner."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest
from deploy_testkit import Env, Stubber

LOGINCTL = """#!/bin/bash
echo "loginctl $*" >> "$STUB_LOG"
case "$*" in
  *enable-linger*) touch "$STUB_LOG.linger" ;;
  *show-user*) if [[ -e "$STUB_LOG.linger" ]]; then echo yes; else echo "${LINGER:-yes}"; fi ;;
esac
"""


@pytest.fixture
def stub_bin(tmp_path: Path) -> tuple[Path, Stubber]:
    """Return a bin dir for PATH plus a function that writes a logging stub into it."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "loginctl").write_text(LOGINCTL)  # lingering on, unless a test flips LINGER
    (bin_dir / "loginctl").chmod(0o755)

    def stub(name: str, body: str = "") -> None:
        path = bin_dir / name
        path.write_text(f'#!/bin/bash\necho "{name} $*" >> "$STUB_LOG"\n{body}\n')
        path.chmod(path.stat().st_mode | stat.S_IXUSR)

    return bin_dir, stub


@pytest.fixture
def box(tmp_path: Path, stub_bin: tuple[Path, Stubber]) -> tuple[Env, Stubber]:
    """Return a runner Env plus the stub writer sharing one bin dir."""
    return Env(tmp_path, stub_bin[0]), stub_bin[1]
