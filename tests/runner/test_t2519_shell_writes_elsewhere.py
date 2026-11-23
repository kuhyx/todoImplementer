"""T2519: free workers and board turns wrote into OTHER repos' checkouts by shell, and nothing saw it."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from todoimpl.runner import freeworker, srcguard

SHIM = """#!/bin/sh
echo worker > made.txt
git add made.txt && git commit -qm worker
echo stray > "$STRAY"
exit 0
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _checkout(src: Path, name: str) -> Path:
    """Make kuhy's checkout `<src>/<name>` with a.txt and e.txt committed."""
    repo = src / name
    repo.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        _git(repo, *args)
    for file in ("a.txt", "e.txt"):
        (repo / file).write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _worker_world(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bin_dir: Path
) -> tuple[Path, Path, list[str]]:
    """Return (kuhy's app checkout, his other checkout, worker argv): the child's worktree hangs off app."""
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    app, other = _checkout(src, "app"), _checkout(src, "other")
    run = tmp_path / "umbrella"
    wt = run / "children" / "umbr0001-3" / "wt"
    _git(app, "worktree", "add", "-q", "-b", "child", str(wt))
    shim = bin_dir / "claude-free"
    shim.write_text(SHIM, encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("STRAY", str(other / "a.txt"))
    (tmp_path / "task.md").write_text("Do the thing.", encoding="utf-8")
    argv = [str(wt), str(tmp_path / "task.md"), str(wt.parent / "w.log"), "--issues", str(run)]
    return app, other, [*argv, "--child", "kuhyx/app"]


@pytest.mark.skipif(shutil.which("bwrap") is None, reason="needs bubblewrap")
def test_t2519_a_free_worker_cannot_write_other_checkouts_by_shell_yet_commits_in_its_worktree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    monkeypatch.setenv("PATH", f"{bin_dir}:/usr/bin:/bin")
    app, other, argv = _worker_world(tmp_path, monkeypatch, bin_dir)
    assert freeworker.main(argv) == 0
    assert (other / "a.txt").read_text(encoding="utf-8") == "base\n"  # the shell write hit a read-only src
    log = subprocess.run(
        ["git", "log", "-1", "--format=%s", "child"], cwd=app, capture_output=True, check=True
    )
    assert log.stdout.decode().strip() == "worker"  # its own git dir (inside kuhy's .git) stayed writable
    assert not (app / "made.txt").exists()
    assert not (tmp_path / "umbrella" / "children" / "umbr0001-3" / srcguard.LOG).exists()


def test_t2519_with_no_bwrap_the_worker_runs_and_its_write_elsewhere_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
    monkeypatch.setenv("PATH", str(bin_dir))  # no bwrap on PATH
    _app, other, argv = _worker_world(tmp_path, monkeypatch, bin_dir)
    assert freeworker.main(argv) == 0
    issues = (tmp_path / "umbrella" / "free-issues.jsonl").read_text(encoding="utf-8")
    assert "bwrap is not installed" in issues
    assert f"kuhy's checkout {other} changed while this turn ran: a.txt" in issues
    card = tmp_path / "umbrella" / "children" / "umbr0001-3"
    assert srcguard.owner(card.parent, other, ["a.txt"]) == "umbr0001-3"


def test_t2519_a_turn_that_writes_another_checkout_by_shell_is_logged_for_its_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    app, other = _checkout(src, "app"), _checkout(src, "other")
    (other / "e.txt").write_text("kuhy\n", encoding="utf-8")  # his own edit, there before the turn
    (src / "notes").mkdir()  # not a repo: never scanned
    root = tmp_path / "root"
    run = root / "card0001-0"
    run.mkdir(parents=True)
    said: list[str] = []
    srcguard.begin(run, "implement-1", "kuhyx/app")
    (other / "a.txt").write_text("board\n", encoding="utf-8")
    (other / "new.txt").write_text("board\n", encoding="utf-8")
    (app / "a.txt").write_text("board\n", encoding="utf-8")
    (src / "notes" / "x.txt").write_text("x\n", encoding="utf-8")
    srcguard.end(run, "implement-1", "kuhyx/app", 5.0, said.append)
    assert sorted(said) == [
        f"kuhy's checkout {other} changed while this turn ran: a.txt new.txt",
        f"this turn left edits in kuhy's checkout {app}: a.txt",
    ]
    rows = [json.loads(line) for line in (run / srcguard.LOG).read_text(encoding="utf-8").splitlines()]
    assert sorted((r["checkout"], sorted(r["files"]), r["card"]) for r in rows) == [
        (str(app), ["a.txt"], "card0001-0"),
        (str(other), ["a.txt", "new.txt"], "card0001-0"),
    ]
    assert srcguard.owner(root, other, ["a.txt", "new.txt"]) == "card0001-0"
    assert srcguard.owner(root, other, ["e.txt"]) is None  # kuhy's


@pytest.mark.parametrize("bwrap", ["#!/bin/sh\nexit 1\n", "#!/no/such/shell\n"])
def test_t2519_a_bwrap_that_cannot_sandbox_runs_the_worker_unwalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bwrap: str
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "git").symlink_to(shutil.which("git") or "/usr/bin/git")
    (bin_dir / "bwrap").write_text(bwrap, encoding="utf-8")
    (bin_dir / "bwrap").chmod(0o755)
    monkeypatch.setenv("PATH", str(bin_dir))
    _app, other, argv = _worker_world(tmp_path, monkeypatch, bin_dir)
    assert freeworker.main(argv) == 0
    issues = (tmp_path / "umbrella" / "free-issues.jsonl").read_text(encoding="utf-8")
    assert "bwrap cannot make a sandbox here" in issues
    assert (other / "a.txt").read_text(encoding="utf-8") == "stray\n"


def test_t2519_an_edit_two_cards_saw_has_no_owner_and_old_snapshots_still_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    other = _checkout(src, "other")
    root = tmp_path / "root"
    for card in ("card0001-0", "card0002-0"):
        (root / card).mkdir(parents=True)
        srcguard.begin(root / card, "implement-1", None)
    (other / "a.txt").write_text("someone\n", encoding="utf-8")
    for card in ("card0001-0", "card0002-0"):
        srcguard.end(root / card, "implement-1", None, 5.0, print)
    assert srcguard.owner(root, other, ["a.txt"]) is None  # both ran while it landed
    run = root / "card0003-0"
    run.mkdir()
    old = {"checkout": str(other), "files": {}}  # what a server before T2519 kept
    (run / f"fix-1{srcguard.SNAPSHOT}").write_text(json.dumps(old), encoding="utf-8")
    assert srcguard.end(run, "fix-1", None, 6.0, print) == [str(other / "a.txt")]
    gone: dict[str, dict[str, dict[str, str]]] = {
        "checkouts": {str(src / "gone"): {}}
    }  # a checkout deleted during the turn
    (run / f"fix-2{srcguard.SNAPSHOT}").write_text(json.dumps(gone), encoding="utf-8")
    assert srcguard.end(run, "fix-2", None, 7.0, print) == []
