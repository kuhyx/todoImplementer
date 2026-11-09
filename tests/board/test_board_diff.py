"""worktree_diff against a real throwaway git repo (hermetic HOME, no network)."""

import subprocess
from pathlib import Path

import pytest
from todoimpl.board import diff as diff_mod
from todoimpl.board.diff import worktree_diff


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", "/dev/null")
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "-q", "-b", "main")
    (root / "a.txt").write_text("one\ntwo\n", encoding="utf-8")
    git(root, "add", "a.txt")
    git(root, "commit", "-q", "-m", "base")
    return root


def test_no_worktree_gives_none(tmp_path: Path) -> None:
    assert worktree_diff(None, None) is None
    assert worktree_diff(str(tmp_path / "gone"), None) is None


def test_diff_covers_edits_untracked_and_commits_without_touching_the_index(repo: Path) -> None:
    base = git(repo, "rev-parse", "HEAD")
    (repo / "a.txt").write_text("one\ntwo\nthree\n", encoding="utf-8")
    (repo / "new.txt").write_text("x\ny\n", encoding="utf-8")
    (repo / "bin.dat").write_bytes(b"\x00\x01\x02")
    got = worktree_diff(str(repo), base)
    assert got is not None
    files = {f["path"]: (f["added"], f["removed"]) for f in got["files"]}
    assert files == {"a.txt": (1, 0), "new.txt": (2, 0), "bin.dat": (0, 0)}
    assert "+three" in got["patch"]
    assert got["truncated"] is False
    assert git(repo, "status", "--porcelain").count("??") == 2
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "work")
    assert worktree_diff(str(repo), base) == got
    assert worktree_diff(str(repo), None) == {"files": [], "patch": "", "truncated": False}


def test_patch_is_capped(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diff_mod, "PATCH_CAP", 20)
    (repo / "a.txt").write_text("x" * 500, encoding="utf-8")
    got = worktree_diff(str(repo), "HEAD")
    assert got is not None
    assert (len(got["patch"]), got["truncated"]) == (20, True)


def test_git_failure_gives_an_empty_diff(repo: Path) -> None:
    got = worktree_diff(str(repo), "no-such-ref")
    assert got == {"files": [], "patch": "", "truncated": False}


def test_missing_git_binary_gives_an_empty_diff(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", "/nonexistent")
    assert worktree_diff(str(repo), "HEAD") == {"files": [], "patch": "", "truncated": False}


def test_git_timeout_gives_an_empty_diff(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def hang(*_a: object, **_k: object) -> None:
        cmd = "git"
        raise subprocess.TimeoutExpired(cmd, 1)

    monkeypatch.setattr(subprocess, "run", hang)
    assert worktree_diff(str(repo), "HEAD") == {"files": [], "patch": "", "truncated": False}


def test_t1880_non_utf8_file_in_the_worktree_does_not_crash_the_diff(repo: Path) -> None:
    (repo / "latin1.txt").write_bytes(b"zaj\xf3c\n")
    got = worktree_diff(str(repo), None)
    assert got is not None
    assert [f["path"] for f in got["files"]] == ["latin1.txt"]
    assert "zaj" in got["patch"]
