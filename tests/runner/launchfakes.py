"""Helpers for the launcher and host tests: a run dir with an invocation, a fake systemd, a liveness probe."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING, Any

from todoimpl.runner import claude, launch, orphans

if TYPE_CHECKING:
    from pathlib import Path

    import pytest
    from runnerfakes import Env

STEM = "implement-1.000"


def rig(world: Env, tmp_path: Path) -> tuple[Path, claude.Invocation]:
    run_dir = tmp_path / "abcd1234-0"
    run_dir.mkdir()
    wt = tmp_path / "abcd1234-demo"
    wt.mkdir()
    return run_dir, claude.build("implement", "go", wt)


def invoke(run_dir: Path, inv: claude.Invocation) -> None:
    launch._write_private(run_dir / f"{STEM}.invoke.json", launch._invocation(inv))


def gone(pid: int) -> bool:
    return not orphans.alive(pid, orphans.start_of(pid))


def calls(monkeypatch: pytest.MonkeyPatch, code: int = 0, err: str = "") -> list[list[str]]:
    seen: list[list[str]] = []

    def fake(argv: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return subprocess.CompletedProcess(argv, code, "", err)

    monkeypatch.setattr(launch, "_run", fake)
    return seen
