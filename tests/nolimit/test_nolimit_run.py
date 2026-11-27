"""One repo's visit: fixes only in the board worktree, pushed and deployed when green, else discarded."""

from __future__ import annotations

import json

import pytest
from nolimitfakes import kuhy_repo, remote_log
from runnerfakes import Env, sh
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import fixes, repos, run, status, worktree

NOW = 1_800_000_000.0
FIX = [("fix-demo", "echo fixed >> README.md")]


def load(world: Env, name: str = "demo") -> repos.Repo:
    found = repos.load(world.src / name)
    assert found is not None
    return found


def records() -> list[dict[str, object]]:
    path = state_base() / "app-errors" / "nolimit.json"
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


@pytest.fixture
def fixing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixes, "autofix", lambda _wt: FIX)


@pytest.mark.usefixtures("fixing")
def test_t2543_kuhys_checkout_stays_as_it_was(world: Env) -> None:
    checkout = kuhy_repo(world, test="grep -q fixed README.md")
    (checkout / "README.md").write_text("kuhy's unsaved edit\n", encoding="utf-8")
    before = sh(checkout, "git", "status", "--short")
    assert run.visit(load(world), NOW, push=False) == status.GREEN
    assert sh(checkout, "git", "status", "--short") == before
    assert (checkout / "README.md").read_text(encoding="utf-8") == "kuhy's unsaved edit\n"
    tree = worktree.home() / "demo"
    assert sh(tree, "git", "branch", "--show-current").strip() == worktree.branch_of(NOW)
    assert sh(tree, "git", "log", "-1", "--format=%s").strip() == "Apply lint and format autofixes"
    assert remote_log(world) == ["commands", "init"]  # --no-push


@pytest.mark.usefixtures("fixing")
def test_t2544_a_red_gate_discards_the_commit_and_files_each_failure_once(world: Env) -> None:
    kuhy_repo(world, test="echo 'FAILED tests/a.py::t1'; echo 'FAILED tests/a.py::t2'; exit 1")
    for _ in range(2):
        assert run.visit(load(world), NOW) == status.RED
    tree = worktree.home() / "demo"
    assert sh(tree, "git", "log", "-1", "--format=%s").strip() == "commands"
    assert not worktree.dirty(worktree.Tree(tree, "x", "main"))
    found = records()
    assert [(r["app"], r["repo"], r["count"]) for r in found] == [("demo", "kuhyx/demo", 2)] * 2
    assert len({r["signature"] for r in found}) == 2
    assert all(str(r["signature"]).startswith("nolimit-gate-") for r in found)
    assert remote_log(world) == ["commands", "init"]


@pytest.mark.usefixtures("fixing")
def test_t2545_a_green_gate_pushes_fast_forward_and_deploys(world: Env) -> None:
    log = world.tmp / "deploy.log"
    kuhy_repo(world, test="true", deploy=f"echo deployed >> {log}")
    (state_base() / "app-errors").mkdir(parents=True)
    old = {"app": "demo", "repo": "kuhyx/demo", "signature": "nolimit-gate", "open": True, "count": 1}
    (state_base() / "app-errors" / "nolimit.json").write_text(json.dumps({"errors": [old]}), encoding="utf-8")
    assert run.visit(load(world), NOW) == status.DEPLOYED
    assert remote_log(world)[0] == "Apply lint and format autofixes"
    assert log.read_text(encoding="utf-8") == "deployed\n"
    assert [r["open"] for r in records()] == [False]  # green: the old failure is resolved
    assert run.visit(load(world), NOW) == status.DEPLOYED  # README changes again: one more fix


def test_green_with_nothing_to_commit_or_no_deploy(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])
    assert run.visit(load(world), NOW) == status.GREEN
    monkeypatch.setattr(fixes, "autofix", lambda _wt: FIX)
    assert run.visit(load(world), NOW) == status.PUSHED
    kuhy_repo(world, "none", test="true", deploy="none (a library)")
    assert run.visit(load(world, "none"), NOW) == status.PUSHED


@pytest.mark.usefixtures("fixing")
def test_a_red_push_or_deploy_is_red(world: Env) -> None:
    kuhy_repo(world, test="true", deploy="exit 2")
    assert run.visit(load(world), NOW) == status.RED
    assert records()[0]["signature"] == "nolimit-deploy"
    kuhy_repo(world, "moved", test="true")
    bare = world.tmp / "remotes" / "moved.git"
    other = world.tmp / "other"
    sh(world.tmp, "git", "clone", "-q", str(bare), str(other))
    (other / "x").write_text("x", encoding="utf-8")
    sh(other, "git", "add", "x")
    sh(other, "git", "commit", "-qm", "theirs")
    repo = load(world, "moved")
    tree = worktree.prepare(repo, NOW)
    sh(other, "git", "push", "-q", "origin", "main")  # origin moves on after the worktree was made
    visit = run.Visit(repo, NOW, lambda: True, push=True)
    assert visit._gate(tree, "true") == status.RED  # not a fast-forward: never pushed
    assert remote_log(world, "moved")[0] == "theirs"


def test_a_red_autofix_or_setup(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [("fix-a", "echo a >> README.md"), ("fix-b", "exit 2")])
    assert run.visit(load(world), NOW) == status.RED  # filed; the gate ran on the unfixed tree
    assert remote_log(world) == ["commands", "init"]
    monkeypatch.setattr(fixes, "setup", lambda _wt: [("setup-x", "exit 1")])
    assert run.visit(load(world), NOW) == status.RED
    assert {r["signature"] for r in records()} == {"nolimit-fix-b", "nolimit-setup-x"}


def test_a_failed_commit_hook_is_red(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    checkout = kuhy_repo(world, test="true")
    hook = checkout / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\necho hook says no\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    monkeypatch.setattr(fixes, "autofix", lambda _wt: FIX)
    assert run.visit(load(world), NOW) == status.RED
    assert records()[0]["signature"] == "nolimit-commit"


def test_passing_setup_steps_lead_to_the_gate(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="test -f deps.txt", files={".gitignore": "deps.txt\n"})
    monkeypatch.setattr(fixes, "setup", lambda _wt: [("setup-a", "touch deps.txt"), ("setup-b", "true")])
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])
    assert run.visit(load(world), NOW) == status.GREEN


def test_a_setup_that_changes_the_tree_is_red(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    kuhy_repo(world, test="true")
    monkeypatch.setattr(fixes, "setup", lambda _wt: [("setup-a", "echo x >> README.md")])
    assert run.visit(load(world), NOW) == status.RED
    [record] = records()
    assert record["signature"] == "nolimit-setup-dirty"
    assert "README.md" in str(record["detail"])
    assert remote_log(world) == ["commands", "init"]
