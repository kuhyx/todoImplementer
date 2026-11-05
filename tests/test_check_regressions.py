import subprocess
from pathlib import Path

import check_regressions


def make_repo(tmp_path: Path, rows: str, py_tests: str = "", ts_tests: str = "") -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "tests/regressions").mkdir(parents=True)
    (tmp_path / "tests/regressions/DOCS-server.md").write_text("| Id | What | Test |\n|---|---|---|\n" + rows)
    (tmp_path / "tests/test_x.py").write_text(py_tests)
    (tmp_path / "web/src").mkdir(parents=True)
    (tmp_path / "web/src/a.test.ts").write_text(ts_tests)
    (tmp_path / "web/src/a.ts").write_text("[T99]\n")
    return tmp_path


def test_matching_rows_and_tags_pass(tmp_path: Path) -> None:
    repo = make_repo(
        tmp_path,
        "| T1 | bug | x |\n| T2 | bug | y |\n",
        "def test_t1_bug() -> None:\n    pass\n",
        "it('[T2] y')\n",
    )
    assert check_regressions.problems(repo) == []
    assert check_regressions.main([str(repo)]) == 0


def test_row_without_test_and_tag_without_row(tmp_path: Path, capsys: object) -> None:
    repo = make_repo(tmp_path, "| T1 | bug | x |\n", "def test_t7_other() -> None:\n    pass\n")
    assert check_regressions.problems(repo) == ["T1: row has no test", "T7: test has no row"]
    assert check_regressions.main([str(repo)]) == 1
    assert "T1: row has no test" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_empty_tables_pass_and_cwd_default(tmp_path: Path, monkeypatch: object) -> None:
    repo = make_repo(tmp_path, "")
    monkeypatch.chdir(repo)  # type: ignore[attr-defined]
    assert check_regressions.main([]) == 0
