"""A commit right after a green `make fast` of the same tree skips the second full gate (T2410)."""

import runpy
import subprocess
from pathlib import Path

import fast_stamp
import pytest


def make_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("ignored.txt\n")
    (tmp_path / "a.txt").write_text("a\n")
    return tmp_path


def test_t2410_a_recorded_tree_is_fresh_until_any_file_changes(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    assert not fast_stamp.fresh(repo)
    fast_stamp.record(repo, fast_stamp.key(repo))
    assert fast_stamp.fresh(repo)
    (repo / "ignored.txt").write_text("not part of the tree\n")
    assert fast_stamp.fresh(repo)
    (repo / "new.txt").write_text("untracked counts\n")
    assert not fast_stamp.fresh(repo)


def test_t2410_staging_does_not_change_the_key(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    before = fast_stamp.key(repo)
    subprocess.run(["git", "-C", str(repo), "add", "-A"], check=True)
    assert fast_stamp.key(repo) == before
    assert not list((repo / ".git").glob("fast-key-index*"))


def test_t2410_a_tree_changed_during_the_run_is_not_fresh(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    started = fast_stamp.key(repo)
    (repo / "a.txt").write_text("edited while the gate ran\n")
    fast_stamp.record(repo, started)
    assert not fast_stamp.fresh(repo)


def test_t2410_main(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = make_repo(tmp_path)
    assert fast_stamp.main(["check", str(repo)]) == 1
    assert fast_stamp.main(["key", str(repo)]) == 0
    key = capsys.readouterr().out.strip()
    assert fast_stamp.main(["record", str(repo), key]) == 0
    assert fast_stamp.main(["check", str(repo)]) == 0
    assert fast_stamp.main(["nonsense"]) == 2


def test_t2410_runs_as_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.setattr("sys.argv", ["fast_stamp.py", "check", str(repo)])
    with pytest.raises(SystemExit) as stop:
        runpy.run_path(str(Path(fast_stamp.__file__)), run_name="__main__")
    assert stop.value.code == 1
