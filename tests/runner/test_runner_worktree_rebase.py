"""T1864: a reused worktree is rebased onto origin each drive; a conflict is left to the session."""

from pathlib import Path

import pytest
from runnerfakes import Env, FakeClient, make_repo, sh, task
from schedfakes import CARD, PLAN, boot, state, wait
from todoimpl.board.state import RunState
from todoimpl.runner import orphans, ship, worktree
from todoimpl.runner.files import NeedsYouError

ID = "abcd1234-0"


def _upstream(repo: Path, name: str, text: str) -> str:
    """Commit and push a file to origin/main from the main clone; return the new sha."""
    (repo / name).write_text(text, encoding="utf-8")
    sh(repo, "git", "add", name)
    sh(repo, "git", "commit", "-q", "-m", f"upstream {name}")
    sh(repo, "git", "push", "-q", "origin", "main")
    return sh(repo, "git", "rev-parse", "HEAD").strip()


def _commit(wt: Path, name: str, text: str) -> None:
    (wt / name).write_text(text, encoding="utf-8")
    sh(wt, "git", "add", name)
    sh(wt, "git", "commit", "-q", "-m", f"session {name}")


def test_t1864_a_stale_worktree_is_rebased_and_keeps_uncommitted_work(world: Env) -> None:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, ID)
    (wt.path / "README.md").write_text("edited by the session\n", encoding="utf-8")
    new = _upstream(repo, "beats.txt", "s7\n")
    again = worktree.add(repo, world.root, ID)
    assert (again.path / "beats.txt").read_text(encoding="utf-8") == "s7\n"
    assert (again.path / "README.md").read_text(encoding="utf-8") == "edited by the session\n"
    assert again.base_sha == new
    assert not again.conflict


def test_t1864_a_conflict_is_left_in_place_and_flagged(world: Env) -> None:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, ID)
    _commit(wt.path, "hello.txt", "mine\n")
    new = _upstream(repo, "hello.txt", "other\n")
    again = worktree.add(repo, world.root, ID)
    assert again.conflict
    assert again.base_sha == new
    assert "rebase in progress" in sh(again.path, "git", "status")
    assert worktree.add(repo, world.root, ID).conflict  # still unresolved: untouched, still flagged
    assert worktree.has_conflicts(again.path)


def test_t1864_pushed_work_keeps_its_base_so_the_diff_still_shows_it(world: Env) -> None:
    repo = make_repo(world)
    wt = worktree.add(repo, world.root, ID)
    _commit(wt.path, "hello.txt", "mine\n")
    sh(wt.path, "git", "push", "-q", "origin", "HEAD:main")
    head = sh(wt.path, "git", "rev-parse", "HEAD").strip()
    sh(repo, "git", "pull", "-q", "origin", "main")
    _upstream(repo, "later.txt", "others\n")
    again = worktree.add(repo, world.root, ID, prev_base=wt.base_sha)
    assert again.base_sha == wt.base_sha
    assert sh(again.path, "git", "rev-parse", "HEAD").strip() == head
    assert not again.conflict


def test_t1864_attach_rebases_a_run_that_already_has_a_worktree(world: Env) -> None:
    repo = make_repo(world)
    st = RunState(task_id=ID, stage="implement", started_at=0.0, repo="kuhyx/demo")
    worktree.attach(st, "kuhyx/demo", world.root)
    new = _upstream(repo, "beats.txt", "s7\n")
    worktree.attach(st, "kuhyx/demo", world.root)
    assert st.base_sha == new
    assert st.extra["base_branch"] == "main"
    assert "rebase_conflict" not in st.extra
    _commit(Path(str(st.worktree)), "hello.txt", "mine\n")
    _upstream(repo, "hello.txt", "other\n")
    worktree.attach(st, "kuhyx/demo", world.root)
    assert st.extra["rebase_conflict"] == "origin/main"


def test_t1864_the_next_prompt_names_the_conflict(world: Env) -> None:
    sched, _ = boot(world, PLAN)
    repo = world.src / "demo"
    wt = worktree.add(repo, world.root, CARD)
    _commit(wt.path, "hello.txt", "mine\n")
    _upstream(repo, "hello.txt", "other\n")
    try:
        sched.start(CARD)
        wait(lambda: len(world.calls()) >= 1)
        prompt = world.calls()[0]["prompt"]
        assert "rebased onto origin/main and has conflicts: resolve them first" in prompt
        assert state(world).extra["rebase_conflict"] == "origin/main"
    finally:
        sched.close()


def _stale(world: Env) -> tuple[Path, RunState]:
    """Return a run with a worktree, after upstream moved on without touching it."""
    repo = make_repo(world)
    st = RunState(task_id=ID, stage="implement", started_at=0.0, repo="kuhyx/demo")
    worktree.attach(st, "kuhyx/demo", world.root)
    _upstream(repo, "beats.txt", "s7\n")
    return repo, st


def test_t1866_the_ship_drive_never_rebases(world: Env) -> None:
    _, st = _stale(world)
    head = sh(Path(str(st.worktree)), "git", "rev-parse", "HEAD")
    st.stage = "shipping"
    worktree.attach(st, "kuhyx/demo", world.root)
    assert sh(Path(str(st.worktree)), "git", "rev-parse", "HEAD") == head


def test_t1866_a_turn_still_editing_the_tree_is_never_rebased_under_it(world: Env) -> None:
    _, st = _stale(world)
    head = sh(Path(str(st.worktree)), "git", "rev-parse", "HEAD")
    orphans.write(world.root / ID, stem="implement-1", role="implement")
    worktree.attach(st, "kuhyx/demo", world.root)
    assert sh(Path(str(st.worktree)), "git", "rev-parse", "HEAD") == head
    assert st.base_sha == head.strip()


def test_t1866_ship_never_commits_conflict_markers(world: Env) -> None:
    repo, st = _stale(world)
    wt = Path(str(st.worktree))
    (wt / "README.md").write_text("loose edit\n", encoding="utf-8")
    _upstream(repo, "README.md", "upstream edit\n")
    again = worktree.add(repo, world.root, ID)
    assert again.conflict
    remote = world.tmp / "remotes" / "demo.git"
    before = sh(remote, "git", "rev-parse", "main")
    item = FakeClient({"abcd1234": task()}).item("abcd1234")
    plan = ship.ShipPlan(repo, wt, again.branch, item, [], world.root / ID, 10, base_sha=again.base_sha)
    with pytest.raises(NeedsYouError, match="Unresolved conflicts"):
        ship.ship(plan, FakeClient({"abcd1234": task()}), lambda: 1.0)
    assert sh(remote, "git", "rev-parse", "main") == before
