from __future__ import annotations

import runpy
import sqlite3
from contextlib import closing
from typing import TYPE_CHECKING

import pytest
from todoimpl.tokens import schema
from tokens_builders import assistant, prompt, write

if TYPE_CHECKING:
    from pathlib import Path


def test_db_path_prefers_the_env_override(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(schema.ENV_DB, str(tmp_path / "x.sqlite"))
    assert schema.db_path() == tmp_path / "x.sqlite"


def test_db_path_falls_back_to_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(schema.ENV_DB)
    assert schema.db_path() == schema.DEFAULT_DB


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_ingest_module_runs_as_main_into_the_env_db(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = tmp_path / "projects"
    write(root / "proj" / "s1.jsonl", [prompt("go", 0), assistant("m1", 5)])
    db = tmp_path / "out" / "tokens.sqlite"
    monkeypatch.setenv(schema.ENV_DB, str(db))
    monkeypatch.setattr("sys.argv", ["ingest", "--root", str(root), "--budget", "45"])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("todoimpl.tokens.ingest", run_name="__main__")
    assert stop.value.code == 0
    with closing(sqlite3.connect(db)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM turns").fetchone() == (1,)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")
def test_check_window_module_runs_as_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr("sys.argv", ["check_window", "--report-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_module("todoimpl.tokens.check_window", run_name="__main__")
    assert stop.value.code == 1
