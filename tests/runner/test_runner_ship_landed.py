"""T1865: a session may commit and push its own work; Ship ships only what origin lacks, or just closes."""

from pathlib import Path

from runnerfakes import Env, FakeClient, make_repo, sh, task
from schedfakes import CARD, IMPL, LIVE_OK, PLAN, boot, wait_stage
from todoimpl.board.diff import worktree_diff
from todoimpl.runner import ship, worktree


def _plan(repo: Path, wt: worktree.Worktree, world: Env) -> ship.ShipPlan:
    item = FakeClient({"abcd1234": task()}).item("abcd1234")
    return ship.ShipPlan(
        repo, wt.path, wt.branch, item, [], world.root / "abcd1234-0", 10, base_sha=wt.base_sha
    )


def _commit(wt: Path, name: str, text: str = "hi\n") -> None:
    (wt / name).write_text(text, encoding="utf-8")
    sh(wt, "git", "add", name)
    sh(wt, "git", "commit", "-q", "-m", f"session {name}")


def _setup(world: Env) -> tuple[Path, worktree.Worktree, FakeClient, Path]:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, "abcd1234-0")
    return repo, wt, FakeClient({"abcd1234": task()}), world.tmp / "remotes" / "demo.git"


def test_a_branch_the_session_committed_ships(world: Env) -> None:
    repo, wt, client, remote = _setup(world)
    _commit(wt.path, "hello.txt")
    info = ship.ship(_plan(repo, wt, world), client, lambda: 1.0)
    assert sh(remote, "git", "rev-parse", "main").strip() == info["commit"]
    assert client.closed[0][1].startswith(f"Shipped {info['commit'][:12]} to origin/main.")


def test_t1865_a_branch_the_session_pushed_is_closed_without_a_new_commit(world: Env) -> None:
    repo, wt, client, remote = _setup(world)
    _commit(wt.path, "hello.txt")
    _commit(wt.path, "more.txt")
    sh(wt.path, "git", "push", "-q", "origin", "HEAD:main")
    head = sh(wt.path, "git", "rev-parse", "HEAD").strip()
    shown = worktree_diff(str(wt.path), wt.base_sha)
    assert shown is not None
    assert {f["path"] for f in shown["files"]} == {"hello.txt", "more.txt"}
    info = ship.ship(_plan(repo, wt, world), client, lambda: 7.0)
    assert sh(remote, "git", "rev-parse", "main").strip() == head
    assert info == {"commit": head, "closed_at": 7.0}
    shorts = sh(remote, "git", "log", "--reverse", "--format=%h", f"{wt.base_sha}..main").split()
    assert client.closed[0][1].splitlines()[0] == "Pushed by the session: " + ", ".join(shorts) + "."
    assert not wt.path.exists()


def test_t1865_a_pushed_branch_that_origin_moved_past_is_still_closed(world: Env) -> None:
    repo, wt, client, remote = _setup(world)
    _commit(wt.path, "hello.txt")
    sh(wt.path, "git", "push", "-q", "origin", "HEAD:main")
    sh(repo, "git", "pull", "-q", "origin", "main")
    sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "someone else")
    sh(repo, "git", "push", "-q", "origin", "main")
    before = sh(remote, "git", "rev-parse", "main").strip()
    ship.ship(_plan(repo, wt, world), client, lambda: 1.0)
    assert sh(remote, "git", "rev-parse", "main").strip() == before
    assert client.closed[0][1].startswith("Pushed by the session: ")


def test_t1865_partly_pushed_work_squashes_only_what_origin_lacks(world: Env) -> None:
    repo, wt, client, remote = _setup(world)
    _commit(wt.path, "first.txt")
    sh(wt.path, "git", "push", "-q", "origin", "HEAD:main")
    _commit(wt.path, "second.txt")
    (wt.path / "third.txt").write_text("loose\n", encoding="utf-8")
    ship.ship(_plan(repo, wt, world), client, lambda: 1.0)
    assert sh(remote, "git", "log", "--format=%s", "main").splitlines() == [
        "Add hello file",
        "session first.txt",
        "init",
    ]
    assert sh(remote, "git", "show", "main:third.txt") == "loose\n"
    assert sh(remote, "git", "show", "main:first.txt") == "hi\n"


def test_t1865_ship_click_after_the_session_pushed_closes_with_that_evidence(world: Env) -> None:
    sched, client = boot(world, PLAN, IMPL, LIVE_OK, done_check="test -f hello.txt")
    try:
        sched.start(CARD)
        st = wait_stage(world, sched, "gate")
        wt = Path(str(st.worktree))
        sh(wt, "git", "add", "hello.txt")
        sh(wt, "git", "commit", "-q", "-m", "landed by the session")
        sh(wt, "git", "push", "-q", "origin", "HEAD:main")
        shown = worktree_diff(st.worktree, st.base_sha)
        assert shown is not None
        assert [f["path"] for f in shown["files"]] == ["hello.txt"]
        sched.ship(CARD)
        st = wait_stage(world, sched, "shipped")
        assert client.closed[0][1].startswith("Pushed by the session: ")
        assert st.ship is not None
        assert "pushed_at" not in st.ship
        texts = [e["text"] for e in sched.bus.history(CARD, 0)]
        assert any("the session already pushed" in t for t in texts)
        remote = world.tmp / "remotes" / "demo.git"
        assert sh(remote, "git", "log", "-1", "--format=%s", "main") == "landed by the session\n"
    finally:
        sched.close()


def test_t2361_an_untouched_worktree_on_origin_closes_with_no_code_change(world: Env) -> None:
    repo, wt, client, remote = _setup(world)  # the round changed no code: HEAD == base_sha, clean
    before = sh(remote, "git", "rev-parse", "main").strip()
    info = ship.ship(_plan(repo, wt, world), client, lambda: 4.0)
    assert info == {"commit": "", "closed_at": 4.0}
    assert client.closed[0][1].startswith("Closed with no code change.")
    assert sh(remote, "git", "rev-parse", "main").strip() == before
    assert not wt.path.exists()


def test_t2361_an_untouched_worktree_origin_moved_past_still_closes(world: Env) -> None:
    repo, wt, client, remote = _setup(world)
    sh(repo, "git", "commit", "-q", "--allow-empty", "-m", "someone else")
    sh(repo, "git", "push", "-q", "origin", "main")
    before = sh(remote, "git", "rev-parse", "main").strip()
    ship.ship(_plan(repo, wt, world), client, lambda: 1.0)
    assert client.closed[0][1].startswith("Closed with no code change.")
    assert sh(remote, "git", "rev-parse", "main").strip() == before
