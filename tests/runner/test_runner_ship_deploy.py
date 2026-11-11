"""Done means deployed (kuhy, 2026-11-11): Ship deploys what it pushed, per CLAUDE.md, then closes."""

from pathlib import Path

import pytest
from runnerfakes import CLAUDE_MD, NO_DEPLOY_MD, Env, FakeClient, executable, make_repo, sh, task
from todoimpl.runner import ship, worktree
from todoimpl.runner.files import NeedsYouError

REMOTE = "demo.git"


def _setup(
    world: Env, monkeypatch: pytest.MonkeyPatch, md: str = CLAUDE_MD
) -> tuple[Path, worktree.Worktree]:
    repo = make_repo(world, files={"README.md": "demo\n", "CLAUDE.md": md})
    executable(repo / ".git" / "hooks" / "pre-push", f"#!/bin/sh\necho push >> {world.tmp}/pushes\n")
    monkeypatch.setenv("DEPLOY_LOG", str(world.tmp / "deploys"))
    wt = worktree.add(repo, world.root, "abcd1234-0")
    (wt.path / "hello.txt").write_text("hi\n", encoding="utf-8")
    return repo, wt


def _plan(
    world: Env, repo: Path, wt: worktree.Worktree, checks: list[tuple[str, str]] | None = None
) -> ship.ShipPlan:
    item = FakeClient({"abcd1234": task()}).item("abcd1234")
    run_dir = world.root / "abcd1234-0"
    return ship.ShipPlan(repo, wt.path, wt.branch, item, checks or [], run_dir, 10, base_sha=wt.base_sha)


def _count(world: Env, name: str) -> int:
    path = world.tmp / name
    return len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0


def _main(world: Env) -> str:
    return sh(world.tmp / "remotes" / REMOTE, "git", "rev-parse", "main").strip()


def test_t1960_a_repo_without_a_deploy_line_is_pushed_but_not_deployed(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch, NO_DEPLOY_MD)
    client = FakeClient({"abcd1234": task()})
    with pytest.raises(NeedsYouError) as stop:
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert stop.value.kind == "run_failed"
    assert stop.value.text.startswith(
        "pushed, not deployed: kuhyx/demo declares no deploy: command in CLAUDE.md"
    )
    assert _main(world) == sh(wt.path, "git", "rev-parse", "HEAD").strip()  # the code landed
    assert (client.closed, wt.path.exists(), _count(world, "deploys")) == ([], True, 0)


def test_t1960_a_repo_with_no_claude_md_at_all_reads_as_no_deploy_line(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch)
    sh(wt.path, "git", "rm", "-q", "CLAUDE.md")
    with pytest.raises(NeedsYouError, match="pushed, not deployed: kuhyx/demo declares no deploy"):
        ship.ship(_plan(world, repo, wt), FakeClient({"abcd1234": task()}), lambda: 1.0)


def test_t1961_a_failed_deploy_keeps_the_note_open_and_a_retry_never_pushes_twice(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch)
    client = FakeClient({"abcd1234": task()})
    monkeypatch.setenv("DEPLOY_EXIT", "3")
    with pytest.raises(NeedsYouError) as stop:
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert stop.value.kind == "run_failed"
    assert stop.value.text.startswith("pushed, not deployed: deploy failed (exit 3): ")
    assert "shim-deploy-output" in stop.value.text
    pushed = _main(world)
    assert not (
        wt.path / "deploy-artifact.txt"
    ).exists()  # what the deploy left is cleaned, never squashed in
    (wt.path / "build-leftover.txt").write_text("a deploy leaves files behind\n", encoding="utf-8")
    monkeypatch.setenv("DEPLOY_EXIT", "0")
    info = ship.ship(_plan(world, repo, wt), client, lambda: 2.0)
    assert (_main(world), _count(world, "pushes"), _count(world, "deploys")) == (pushed, 1, 2)
    assert info == {"commit": pushed, "pushed_at": 1.0, "closed_at": 2.0}
    assert client.closed[0][1].startswith(f"Shipped {pushed[:12]} to origin/main.")
    assert not wt.path.exists()


def test_t1962_a_passing_deploy_goes_into_the_evidence_and_the_note_closes(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch)
    client = FakeClient({"abcd1234": task()})
    info = ship.ship(_plan(world, repo, wt, [("done_check", "test -f hello.txt")]), client, lambda: 5.0)
    assert info["closed_at"] == 5.0
    lines = client.closed[0][1].splitlines()
    assert lines[0] == f"Shipped {info['commit'][:12]} to origin/main."
    assert lines[1].startswith("done_check `test -f hello.txt` exit 0")
    assert lines[2].startswith("deploy `echo deployed")
    assert lines[2].endswith("exit 0:")
    assert lines[3] == "shim-deploy-output"
    assert _count(world, "deploys") == 1


def test_t1962_the_deploy_line_is_read_from_the_pushed_commit_not_from_the_main_checkout(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch, NO_DEPLOY_MD)  # ~/src/demo declares nothing
    (wt.path / "CLAUDE.md").write_text(CLAUDE_MD, encoding="utf-8")  # this change adds the line
    client = FakeClient({"abcd1234": task()})
    ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert (_count(world, "deploys"), len(client.closed)) == (1, 1)


def test_t1962_a_close_with_no_code_change_deploys_nothing(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch, NO_DEPLOY_MD)  # nothing pushed: no deploy line is needed either
    (wt.path / "hello.txt").unlink()
    client = FakeClient({"abcd1234": task()})
    info = ship.ship(_plan(world, repo, wt), client, lambda: 3.0, allow_empty=True)
    assert info == {"commit": "", "closed_at": 3.0}
    assert (_count(world, "deploys"), _count(world, "pushes"), len(client.closed)) == (0, 0, 1)
    assert client.closed[0][1].startswith("Closed with no code change.")


def _session_pushed(wt: worktree.Worktree) -> str:
    sh(wt.path, "git", "add", "hello.txt")
    sh(wt.path, "git", "commit", "-q", "-m", "session work")
    sh(wt.path, "git", "push", "-q", "origin", "HEAD:main")
    return sh(wt.path, "git", "rev-parse", "HEAD").strip()


def test_t1964_work_the_session_pushed_is_checked_again_before_it_is_deployed(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch)
    client = FakeClient({"abcd1234": task()})
    _session_pushed(wt)
    with pytest.raises(
        NeedsYouError, match="Checks went red after the rebase on origin/main: done_check"
    ) as red:
        ship.ship(_plan(world, repo, wt, [("done_check", "false")]), client, lambda: 1.0)
    assert red.value.kind == "checks_failed"
    assert (_count(world, "deploys"), client.closed) == (0, [])


def test_t1964_green_checks_then_the_deploy_for_work_the_session_pushed(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch)
    client = FakeClient({"abcd1234": task()})
    head = _session_pushed(wt)
    info = ship.ship(_plan(world, repo, wt, [("done_check", "test -f hello.txt")]), client, lambda: 4.0)
    assert info == {"commit": head, "closed_at": 4.0}
    lines = client.closed[0][1].splitlines()
    assert lines[0].startswith("Pushed by the session: ")
    assert any(line.startswith("done_check `test -f hello.txt` exit 0") for line in lines)
    assert any(line.startswith("deploy `") for line in lines)
    assert _count(world, "deploys") == 1


def test_t1964_work_the_session_pushed_still_needs_a_deploy_line(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, wt = _setup(world, monkeypatch, NO_DEPLOY_MD)
    client = FakeClient({"abcd1234": task()})
    _session_pushed(wt)
    with pytest.raises(NeedsYouError, match="pushed, not deployed: kuhyx/demo declares no deploy"):
        ship.ship(_plan(world, repo, wt), client, lambda: 1.0)
    assert client.closed == []
