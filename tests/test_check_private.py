import subprocess
from pathlib import Path

import check_private
import pytest

LIST = "# comment\n\nsecretword\nre:\\bTK-\\d+\n"


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    deny = tmp_path / "deny.txt"
    deny.write_text(LIST)
    monkeypatch.setenv(check_private.ENV_VAR, str(deny))
    return root


def test_clean_repo_passes(repo: Path) -> None:
    (repo / "a.txt").write_text("nothing here\n")
    assert check_private.main(["--root", str(repo)]) == 0


def test_content_hit_is_case_insensitive(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (repo / "a.txt").write_text("fine\nSecretWord inside\n")
    assert check_private.main(["--root", str(repo)]) == 1
    assert "a.txt:2" in capsys.readouterr().out


def test_regex_and_path_hits(repo: Path) -> None:
    (repo / "TK-12.txt").write_text("x\n")
    hits = check_private.scan_repo(repo, check_private.load_patterns(check_private.denylist_path()))
    assert {hit.where for hit in hits} == {"TK-12.txt"}


def test_binary_files_are_skipped(repo: Path) -> None:
    (repo / "b.bin").write_bytes(b"\0secretword")
    assert check_private.main(["--root", str(repo)]) == 0


def test_commit_message_scanned(repo: Path, tmp_path: Path) -> None:
    assert check_private.main(["--root", str(repo), "--message", "all good"]) == 0
    assert check_private.main(["--root", str(repo), "--message", "mentions secretword"]) == 1
    msg = tmp_path / "msg"
    msg.write_text("fix TK-9")
    assert check_private.main(["--root", str(repo), "--message-file", str(msg)]) == 1


def test_missing_denylist_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv(check_private.ENV_VAR, str(tmp_path / "absent.txt"))
    assert check_private.main(["--root", str(repo)]) == 2


def test_empty_denylist_fails_closed(repo: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    empty = tmp_path / "empty.txt"
    empty.write_text("# only a comment\n")
    monkeypatch.setenv(check_private.ENV_VAR, str(empty))
    assert check_private.main(["--root", str(repo)]) == 2


def test_default_path_is_under_home(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv(check_private.ENV_VAR, raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    assert check_private.denylist_path() == tmp_path / ".config/todoImplementer/private-denylist.txt"


def test_word_boundary_regex_ignores_embedded_words(
    repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    deny = tmp_path / "wb.txt"
    deny.write_text("re:\\bsecretive\\b\n")
    monkeypatch.setenv(check_private.ENV_VAR, str(deny))
    (repo / "pnpm-lock.yaml").write_text("'@azure/keysecretive-secrets': ^4\n")
    assert check_private.main(["--root", str(repo)]) == 0
    (repo / "other.txt").write_text("the Secretive path\n")
    assert check_private.main(["--root", str(repo)]) == 1
