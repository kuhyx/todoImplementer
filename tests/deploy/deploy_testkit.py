"""Shared helpers for the deploy tests (unique module name: no clash with other conftests)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from typing import Protocol

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"
sys.path.insert(0, str(DEPLOY))


class Stubber(Protocol):
    """Writes a logging stub CLI named `name`, optionally with extra shell `body`."""

    def __call__(self, name: str, body: str = "") -> None:
        """Create the stub."""


class Env:
    """Run a script with stubs first on PATH, a temp HOME and a call log."""

    def __init__(self, tmp: Path, bin_dir: Path) -> None:
        """Create HOME and the call log under tmp, with bin_dir first on PATH."""
        self.home = tmp / "home"
        self.home.mkdir()
        self.log = tmp / "calls.log"
        self.log.touch()
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "STUB_LOG": str(self.log),
            "TODOIMPL_BUILD_ID": "abc1234",
        }

    def run(self, *argv: str, stdin: str = "", **extra: str) -> subprocess.CompletedProcess[str]:
        """Run argv with extra env vars; never raises on a non-zero exit."""
        return subprocess.run(
            [*argv],
            input=stdin,
            capture_output=True,
            text=True,
            env={**self.env, **extra},
            timeout=40,
            check=False,
        )

    @property
    def calls(self) -> str:
        """Return the stub call log so far."""
        return self.log.read_text()

    @property
    def env_file(self) -> Path:
        """Return the path of the oauth2-proxy env file under the temp HOME."""
        return self.home / ".config" / "todoImplementer" / "oauth2-proxy.env"
