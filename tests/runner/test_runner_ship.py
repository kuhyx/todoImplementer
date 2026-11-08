from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, make_repo, sh, task
from todoimpl.runner import ship, worktree
from todoimpl.runner.files import NeedsYouError


def _plan(
    world: Env, repo: Path, wt: worktree.Worktree, checks: list[tuple[str, str]] | None = None
) -> ship.ShipPlan:
    item = FakeClient({"abcd1234": task()}).item("abcd1234")
    return ship.ShipPlan(repo, wt.path, wt.branch, item, checks or [], world.root / "abcd1234-0", 10)


def _setup(world: Env) -> tuple[Path, worktree.Worktree, FakeClient]:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, "abcd1234-0")
    (wt.path / "hello.txt").write_text("hi\n", encoding="utf-8")
    return repo, wt, FakeClient({"abcd1234": task()})


def test_commit_message_keeps_subject_short_and_adds_the_trailer() -> None:
    assert ship.commit_message("Add  hello\nfile", "abcd1234") == "Add hello file\n\nTodo: abcd1234\n"
    long = ship.commit_message("x" * 80, "abcd1234").splitlines()[0]
    assert len(long) == 50
    assert long.endswith("…")
    assert ship.commit_message("  ", "abcd1234").startswith("Todo abcd1234\n")


def test_ship_squashes_rebases_pushes_closes_and_cleans_up(world: Env) -> None:
    repo, wt, client = _setup(world)
    sh(wt.path, "git", "add", "hello.txt")
    sh(wt.path, "git", "commit", "-q", "-m", "wip by the implementer")
    (wt.path / "more.txt").write_text("more\n", encoding="utf-8")
    sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "upstream moved")
    sh(repo, "git", "push", "-q", "origin", "main")
    info = ship.ship(_plan(world, repo, wt, [("done_check", "test -f hello.txt")]), client, lambda: 42.0)
    remote = world.tmp / "remotes" / "demo.git"
    assert sh(remote, "git", "log", "-1", "--format=%B", "main") == "Add hello file\n\nTodo: abcd1234\n\n"
    assert sh(remote, "git", "rev-parse", "main").strip() == info["commit"]
    assert sh(remote, "git", "log", "--format=%s", "main").splitlines() == [
        "Add hello file",
        "upstream moved",
        "init",
    ]
    assert info == {"commit": info["commit"], "pushed_at": 42.0, "closed_at": 42.0}
    assert client.closed[0][0] == "abcd1234-0"
    assert (
        client.closed[0][1]
        == f"Shipped {info['commit'][:12]} to origin/main.\ndone_check `test -f hello.txt` exit 0:"
    )
    assert not wt.path.exists()


def test_evidence_without_checks() -> None:
    shipped = "Shipped 0123456789ab to origin/main."
    assert ship.evidence("0123456789abcdef", "main", []) == f"{shipped}\nNo checks were found."
    assert (
        ship.evidence("0123456789abcdef", "main", [], "live: a: done")
        == f"{shipped}\nlive: a: done\nNo checks were found."
    )


def test_ship_with_nothing_to_ship(world: Env) -> None:
    repo, wt, client = _setup(world)
    (wt.path / "hello.txt").unlink()
    with pytest.raises(NeedsYouError, match="Nothing to ship"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)


def test_ship_conflict_aborts_the_rebase(world: Env) -> None:
    repo, wt, client = _setup(world)
    (repo / "hello.txt").write_text("other\n", encoding="utf-8")
    sh(repo, "git", "add", "hello.txt")
    sh(repo, "git", "commit", "-q", "-m", "clash")
    sh(repo, "git", "push", "-q", "origin", "main")
    with pytest.raises(NeedsYouError, match=r"conflicts in hello\.txt"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert not (wt.path / ".git").is_file() or "rebase" not in sh(wt.path, "git", "status")
    assert client.closed == []


def test_ship_stops_on_red_checks(world: Env) -> None:
    repo, wt, client = _setup(world)
    with pytest.raises(NeedsYouError, match="red after the rebase") as red:
        ship.ship(_plan(world, repo, wt, [("tests", "exit 1")]), client, lambda: 1.0)
    assert red.value.kind == "checks_failed"


def test_ship_reports_a_refused_push(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, wt, client = _setup(world)
    monkeypatch.setenv("GIT_PUSH_ALLOW_ROOT", "/nowhere")
    with pytest.raises(NeedsYouError, match="was refused"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert client.closed == []
    assert wt.path.exists()


def test_ship_reports_a_failed_close(world: Env) -> None:
    repo, wt, client = _setup(world)
    client.fail_close = True
    with pytest.raises(NeedsYouError, match="closing the note failed"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)


def test_t303_ship_waits_for_a_slow_commit_hook(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, wt, client = _setup(world)
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nsleep 1\n", encoding="utf-8")
    hook.chmod(0o755)
    monkeypatch.setattr(worktree, "GIT_TIMEOUT", 0.5)
    info = ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert info["commit"]


def test_auto_ship_with_no_diff_reports_a_failed_close_and_keeps_the_worktree(world: Env) -> None:
    repo, wt, client = _setup(world)
    (wt.path / "hello.txt").unlink()
    client.fail_close = True
    with pytest.raises(NeedsYouError, match="Nothing to push but closing the note failed"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0, allow_empty=True)
    assert wt.path.exists()
