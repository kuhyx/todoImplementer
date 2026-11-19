"""T2079: a repo's checkout is found by its origin in the likely roots, not only at ~/src/<name>."""

import json
from pathlib import Path

import pytest
from todoimpl.board import repos
from todoimpl.board.board import repo_checker
from todoimpl.board.repos import repo_path

URL = "https://github.com/kuhyx/claude-config.git"


def make_clone(path: Path, url: str | None = URL) -> Path:
    (path / ".git").mkdir(parents=True)
    if url:
        (path / ".git" / "config").write_text(f'[remote "origin"]\n\turl = {url}\n', encoding="utf-8")
    return path


def test_t2079_a_checkout_outside_src_is_found_by_its_origin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = make_clone(tmp_path / "dot" / ".claude")
    monkeypatch.setenv("TODOIMPL_REPO_ROOTS", str(live))
    src = tmp_path / "src"
    src.mkdir()
    assert repo_path("kuhyx/claude-config", src) == live
    assert repo_path("claude-config", src) == live  # a bare name is kuhyx/<name>


def test_t2079_a_repo_nested_one_level_in_a_root_is_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    nested = make_clone(tmp_path / "misc" / "linux_configuration", "git@github.com:kuhyx/linux_configuration")
    monkeypatch.setenv("TODOIMPL_REPO_ROOTS", str(tmp_path / "misc"))
    assert repo_path("kuhyx/linux_configuration", tmp_path / "src") == nested


def test_t2079_src_name_wins_then_the_map(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    other = make_clone(tmp_path / "dot" / ".claude")
    monkeypatch.setenv("TODOIMPL_REPO_ROOTS", str(other))
    direct = make_clone(tmp_path / "src" / "claude-config")
    assert repo_path("kuhyx/claude-config", tmp_path / "src") == direct


def test_t2079_the_override_file_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pinned = make_clone(tmp_path / "pinned", None)
    make_clone(tmp_path / "src" / "claude-config")
    path = tmp_path / "repo-paths.json"
    path.write_text(json.dumps({"kuhyx/claude-config": str(pinned), "a/b": str(tmp_path / "gone")}))
    monkeypatch.setenv("TODOIMPL_REPO_PATHS", str(path))
    src = tmp_path / "src"
    assert repo_path("kuhyx/claude-config", src) == pinned
    assert repo_path("a/b", src) == src / "b"  # a vanished path is ignored
    path.write_text("[1]")  # not an object: ignored
    assert repo_path("kuhyx/claude-config", src) == src / "claude-config"
    path.write_text("{oops")
    assert repo_path("kuhyx/x", src) == src / "x"


def test_t2079_the_map_is_cached_for_ten_minutes_and_rebuilt_on_a_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "root"
    first = make_clone(root / "a", "https://github.com/kuhyx/first")
    monkeypatch.setenv("TODOIMPL_REPO_ROOTS", str(root))
    now = [1000.0]
    monkeypatch.setattr(repos, "_clock", lambda: now[0])
    src = tmp_path / "src"
    assert repo_path("kuhyx/first", src) == first
    second = make_clone(root / "b", "https://github.com/kuhyx/second")
    assert repo_path("kuhyx/second", src) == second  # a miss rebuilds at once
    first.rename(root / "moved")
    assert repo_path("kuhyx/first", src) == root / "moved"  # a vanished hit is a miss
    late = make_clone(root / "c", "https://github.com/KuhyX/Late")
    now[0] += repos.REFRESH_S + 1  # stale: rebuilt even for a hit
    assert repo_path("kuhyx/second", src) == second
    assert repo_path("kuhyx/late", src) == late  # owner and name are case-blind
    assert repo_path("kuhyx/none", src) == src / "none"


def test_t2079_default_roots_cover_claude_and_testsandmisc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TODOIMPL_REPO_ROOTS")
    monkeypatch.setenv("HOME", str(tmp_path))
    live = make_clone(tmp_path / ".claude")
    nested = make_clone(tmp_path / "src" / "testsAndMisc" / "tool", "https://github.com/kuhyx/tool.git")
    thesis = make_clone(tmp_path / "praca_magisterska", "https://github.com/kuhyx/thesis")
    src = tmp_path / "src"
    assert repo_path("kuhyx/claude-config", src) == live
    assert repo_path("kuhyx/tool", src) == nested
    assert repo_path("kuhyx/thesis", src) == thesis


def test_t2079_a_repo_with_no_checkout_is_not_blocked_but_an_absolute_path_is(tmp_path: Path) -> None:
    check = repo_checker()
    assert check("kuhyx/claude-config") is None  # Start clones it
    assert check("claude-config") is None
    assert check(str(tmp_path / "nope")) == str(tmp_path / "nope")
    assert check(str(make_clone(tmp_path / "there", None))) is None
