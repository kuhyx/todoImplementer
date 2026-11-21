"""Ship, Cancel and Done manually free the run's worktrees by themselves (T2433)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from repofakes import IMPL, LIVE, PLAN, Rig
from runnerfakes import make_repo, sh
from todoimpl.repotask import files
from todoimpl.repotask.ids import repo_card_id
from todoimpl.runner.files import write_json

if TYPE_CHECKING:
    from pathlib import Path

PLAIN = "## Fix the parser\nHandle empty input.\ndone_check: true"


def at_gate(rig: Rig) -> tuple[str, Path]:
    """Start a repo card to its gate; the session also added a worktree of another repo in its run dir."""
    repo = rig.repo()
    note = rig.note(repo, "plain note", PLAIN)
    card = repo_card_id(repo)
    write_json(rig.run_dir(card) / files.DONE, {"done": [f"{note}-0"], "steps": {}})
    rig.script(card, PLAN, IMPL, LIVE)
    rig.sched.start(card)
    rig.wait(card, {"gate"})
    other = make_repo(rig.world, "other")
    side = rig.run_dir(card) / "wt-other"
    sh(other, "git", "worktree", "add", "-q", "-b", f"todo/{card}", str(side), "origin/main")
    return card, side


def gone(rig: Rig, *paths: Path) -> None:
    rig.until(lambda: not any(p.exists() for p in paths))


def test_t2433_ship_removes_the_sessions_other_worktrees_too(rig: Rig) -> None:
    card, side = at_gate(rig)
    rig.sched.ship(card)
    rig.wait(card, {"shipped"})
    gone(rig, side, rig.run_dir(card) / "wt")
    assert sh(rig.world.src / "other", "git", "branch", "--format=%(refname:short)").split() == ["main"]
    assert (rig.run_dir(card) / "state.json").is_file()


def test_t2433_cancel_removes_the_clean_worktrees(rig: Rig) -> None:
    card, side = at_gate(rig)
    rig.sched.cancel(card)
    gone(rig, side)
    assert (rig.run_dir(card) / "wt").is_dir()  # the fake session left uncommitted work there: it stays


def test_t2433_done_manually_removes_the_clean_worktrees(rig: Rig) -> None:
    card, side = at_gate(rig)
    rig.sched.done_manually(card, repotask=True)
    gone(rig, side)
    assert (rig.run_dir(card) / "wt").is_dir()
