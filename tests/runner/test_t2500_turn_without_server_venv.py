"""A board turn never inherits the server's venv (T2500).

The server runs from `~/src/todoImplementer/.venv`; a turn copied its env as is, so a worker's `python3` was
the server's venv python (no user site: `import gatelock` failed) and `uv pip install` would write into the
live server's venv. A turn's env drops `VIRTUAL_ENV` and the venv's `bin` from `PATH`, like a gate's (T1836).
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

import pytest
from runnerfakes import Env
from todoimpl.runner import claude


def _turn_env(world: Env) -> dict[str, str]:
    wt = world.root / "c1-0" / "wt"
    wt.mkdir(parents=True, exist_ok=True)
    return claude.build("implement", "p", wt).env


def test_t2500_a_turn_does_not_inherit_the_servers_venv(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    venv = tmp_path / "srv" / ".venv"
    (venv / "bin").mkdir(parents=True)
    (venv / "bin" / "python3").write_text("#!/bin/sh\n", encoding="utf-8")
    (venv / "bin" / "python3").chmod(0o755)
    monkeypatch.setenv("VIRTUAL_ENV", str(venv))
    monkeypatch.setenv("PATH", f"{venv}/bin{os.pathsep}{os.environ['PATH']}")
    env = _turn_env(world)
    assert "VIRTUAL_ENV" not in env
    assert f"{venv}/bin" not in env["PATH"].split(os.pathsep)
    assert str(world.bin) in env["PATH"].split(os.pathsep)  # the rest of PATH stays
    found = shutil.which("python3", path=env["PATH"])
    assert found is None or not found.startswith(str(venv))


def test_the_suites_own_venv_is_dropped_too(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    monkeypatch.setenv("PATH", f"{sys.prefix}/bin{os.pathsep}{os.environ['PATH']}")
    env = _turn_env(world)
    if sys.prefix != sys.base_prefix:
        assert f"{sys.prefix}/bin" not in env["PATH"].split(os.pathsep)
    assert "PYTHONUSERBASE" in env  # T2495 still holds


def test_t2501_the_suite_never_reads_the_calling_turns_user_base() -> None:
    # A board turn runs this suite with PYTHONUSERBASE=<its run>/userbase; real_base must not take it.
    assert "PYTHONUSERBASE" not in os.environ
