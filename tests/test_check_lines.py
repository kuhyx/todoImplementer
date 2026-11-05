import subprocess
from pathlib import Path

import check_lines
from repo_files import repo_files


def make_repo(tmp_path: Path) -> Path:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / ".gitignore").write_text("*.zip\n")
    return tmp_path


def test_over_cap_lists_long_files_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "long.txt").write_text("x\n" * 251)
    (repo / "ok.txt").write_text("x\n" * 250)
    (repo / "uv.lock").write_text("x\n" * 900)
    (repo / "blob.bin").write_bytes(b"\0" * 5000)
    (repo / "nonl.txt").write_text("a\n" * 250 + "b")
    assert check_lines.over_cap(repo) == [("long.txt", 251), ("nonl.txt", 251)]


def test_ignored_zip_is_never_listed(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    (repo / "x.zip").write_bytes(b"PK\0")
    (repo / "a.txt").write_text("a\n")
    status = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain"], check=True, capture_output=True, text=True
    ).stdout
    assert "zip" not in status
    assert check_lines.line_count(repo / "x.zip") == 0
    assert (repo / "x.zip").name not in [p.name for p in repo_files(repo)]


def test_main_exit_codes(tmp_path: Path, capsys: object) -> None:
    repo = make_repo(tmp_path)
    (repo / "a.txt").write_text("a\n")
    assert check_lines.main([str(repo)]) == 0
    (repo / "b.txt").write_text("x\n" * 300)
    assert check_lines.main([str(repo)]) == 1
    assert "b.txt: 300 lines" in capsys.readouterr().out  # type: ignore[attr-defined]


def test_main_defaults_to_cwd(tmp_path: Path, monkeypatch: object) -> None:
    repo = make_repo(tmp_path)
    monkeypatch.chdir(repo)  # type: ignore[attr-defined]
    assert check_lines.main([]) == 0
