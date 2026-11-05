"""The ``python -m`` entry points exit with their main()'s code."""

from __future__ import annotations

import runpy
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.filterwarnings("ignore::RuntimeWarning")


def _run(module: str, argv: list[str], monkeypatch: pytest.MonkeyPatch) -> int:
    monkeypatch.setattr("sys.argv", [module, *argv])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module(module, run_name="__main__")
    assert isinstance(stop.value.code, int)
    return stop.value.code


def test_main_exits_3_without_transcripts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "empty"
    root.mkdir()
    assert _run("todoimpl.tokens.audit", ["--root", str(root), "--no-write"], monkeypatch) == 3


def test_checkup_runs_as_main(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run("todoimpl.tokens.audit.checkup", ["10", "100"], monkeypatch) == 0


def test_notes_runs_as_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    root = tmp_path / "projects"
    root.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    assert _run("todoimpl.tokens.audit.notes", ["--root", str(root), "--out", str(out)], monkeypatch) == 0
