"""T2515: free workers of umbrella 7808ee0a-0 left edits in kuhy's checkouts; board turns had no src rule."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from runnerfakes import Env
from todoimpl.runner import claude, freeworker, srcguard

WRITERS = ("Edit", "Write", "MultiEdit", "NotebookEdit")
LOOSE = {"permission_mode": "bypassPermissions", "add_dirs": ["~"], "disable_hooks": True, "deny": []}
SHIM = """#!/bin/sh
echo worker > made.txt
echo stray > "$STRAY"
"""


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def _checkout(src: Path, name: str = "app") -> Path:
    """Make a clone of kuhyx/<name> under the src root: a.txt, b.txt, d.txt and e.txt committed."""
    repo = src / name
    repo.mkdir(parents=True)
    for args in (["init", "-q", "-b", "main"], ["config", "user.email", "t@x"], ["config", "user.name", "t"]):
        _git(repo, *args)
    for name_ in ("a.txt", "b.txt", "d.txt", "e.txt"):
        (repo / name_).write_text("base\n", encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    return repo


def _denied(argv: tuple[str, ...]) -> tuple[str, ...]:
    return argv[argv.index("--disallowedTools") + 1 :]


def test_t2515_a_loose_board_session_still_cannot_write_in_kuhys_checkouts(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps(LOOSE), encoding="utf-8")
    monkeypatch.setenv("TODOIMPL_POLICY", str(policy))
    inv = claude.build("implement", "p", tmp_path / "wt")
    assert "bypassPermissions" in inv.argv
    assert _denied(inv.argv) == tuple(f"{tool}(/{src}/**)" for tool in WRITERS)
    closing = claude.build("closing", "p", src / "app")  # reads kuhy's checkout itself; Edit is denied anyway
    assert not any(rule.endswith(f"/{src}/**)") for rule in _denied(closing.argv))
    assert (
        "--disallowedTools" not in claude.build("implement", "p", src / "app").argv
    )  # loose and in-checkout: no deny
    monkeypatch.delenv("TODOIMPL_POLICY")
    assert f"Edit(/{src}/**)" in _denied(claude.build("implement", "p", tmp_path / "wt").argv)


def test_t2515_a_turn_that_edits_the_cards_checkout_is_attributed_to_the_card(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    repo = _checkout(src)
    (repo / "b.txt").write_text("kuhy\n", encoding="utf-8")  # his own edits, dirty before the turn
    (repo / "e.txt").write_text("kuhy\n", encoding="utf-8")
    run = tmp_path / "root" / "card0001-0"
    run.mkdir(parents=True)
    said: list[str] = []
    srcguard.begin(run, "implement-1", "kuhyx/app")
    (repo / "a.txt").write_text("board\n", encoding="utf-8")
    (repo / "b.txt").write_text("board\n", encoding="utf-8")
    (repo / "c.txt").write_text("new\n", encoding="utf-8")
    (repo / "d.txt").unlink()
    assert srcguard.end(run, "implement-1", "kuhyx/app", 5.0, said.append) == [
        "a.txt",
        "b.txt",
        "c.txt",
        "d.txt",
    ]
    assert said == [f"this turn left edits in kuhy's checkout {repo}: a.txt b.txt c.txt d.txt"]
    rows = [json.loads(line) for line in (run / srcguard.LOG).read_text(encoding="utf-8").splitlines()]
    assert [(r["stem"], r["checkout"], sorted(r["files"])) for r in rows] == [
        ("implement-1", str(repo), ["a.txt", "b.txt", "c.txt", "d.txt"])
    ]
    assert srcguard.attributed(run, repo, ["a.txt", "c.txt", "d.txt"])
    assert not srcguard.attributed(run, repo, ["a.txt", "e.txt"])  # e.txt is kuhy's
    assert not srcguard.attributed(run, repo, [])
    assert not srcguard.attributed(run, tmp_path, ["a.txt"])  # another checkout
    assert srcguard.owner(run.parent, repo, ["a.txt", "b.txt"]) == "card0001-0"
    (repo / "a.txt").write_text(
        "kuhy again\n", encoding="utf-8"
    )  # he edited it since: not the card's any more
    assert not srcguard.attributed(run, repo, ["a.txt"])
    assert srcguard.owner(run.parent, repo, ["a.txt"]) is None
    assert srcguard.end(run, "implement-1", "kuhyx/app", 6.0, said.append) == []  # consumed once
    srcguard.begin(run, "implement-2", "kuhyx/app")
    assert srcguard.end(run, "implement-2", "kuhyx/app", 7.0, said.append) == []  # nothing new
    assert len(said) == 1


def test_t2515_no_checkout_or_no_snapshot_attributes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TODOIMPL_SRC", str(tmp_path / "src"))
    run = tmp_path / "card0002-0"
    run.mkdir()
    srcguard.begin(run, "plan-1", None)
    srcguard.begin(run, "plan-1", "kuhyx/missing")
    assert not list(run.iterdir())
    assert srcguard.end(run, "plan-1", "kuhyx/missing", 1.0, print) == []
    repo = _checkout(tmp_path / "src")
    _git(repo, "mv", "a.txt", "z.txt")
    assert set(srcguard.snapshot(repo)) == {"z.txt"}  # a rename counts once, under its new name
    assert srcguard.end(run, "plan-1", "kuhyx/app", 1.0, print) == []  # launched by a server before T2515
    assert srcguard.owner(tmp_path, tmp_path / "src" / "app", ["a.txt"]) is None
    assert not srcguard.attributed(run, tmp_path / "src" / "app", ["a.txt"])  # no log at all


def test_t2515_a_free_worker_that_writes_in_its_repos_checkout_is_logged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    src = tmp_path / "src"
    monkeypatch.setenv("TODOIMPL_SRC", str(src))
    repo = _checkout(src)
    run = tmp_path / "umbrella"
    wt = run / "children" / "umbr0001-3" / "wt"
    wt.mkdir(parents=True)
    _git(wt, "init", "-q", "-b", "main")
    shim = tmp_path / "bin" / "claude-free"
    shim.parent.mkdir()
    shim.write_text(SHIM, encoding="utf-8")
    shim.chmod(0o755)
    monkeypatch.setenv("PATH", f"{shim.parent}:/usr/bin:/bin")
    monkeypatch.setenv("STRAY", str(repo / "a.txt"))
    (tmp_path / "task.md").write_text("Do the thing.", encoding="utf-8")
    argv = [str(wt), str(tmp_path / "task.md"), str(wt.parent / "w.log"), "--issues", str(run)]
    assert freeworker.main([*argv, "--child", "kuhyx/app"]) == 0
    assert srcguard.attributed(wt.parent, repo, ["a.txt"])
    issues = (run / "free-issues.jsonl").read_text(encoding="utf-8")
    assert f"left edits in kuhy's checkout {repo}: a.txt" in issues
