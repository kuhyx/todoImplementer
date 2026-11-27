"""The git chores: prune ended cards' trees and branches (T2585), rebase waiting ones onto origin (T2586)."""

from __future__ import annotations

import json

from nolimitfakes import card_tree, commit, kuhy_repo
from runnerfakes import Env, sh
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import cards, prune, rebase

NOW = 1_800_000_000.0


def always() -> bool:
    return True


def branches(world: Env) -> str:
    return sh(world.src / "demo", "git", "branch", "--list", "todo/*")


def records() -> list[dict[str, object]]:
    path = state_base() / "app-errors" / "nolimit.json"
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


def test_t2585_prune_removes_ended_trees_and_pushed_branches_only(world: Env) -> None:
    checkout = kuhy_repo(world, test="true")
    shipped = card_tree(world, "aaaa0001-0", stage="done_manually")
    unpushed = card_tree(world, "aaaa0002-0", stage="cancelled")
    commit(unpushed, "x.txt", "work\n", "unpushed work")
    dirty = card_tree(world, "aaaa0003-0", stage="cancelled")
    (dirty / "new.txt").write_text("not committed\n", encoding="utf-8")
    waiting = card_tree(world, "aaaa0004-0", stage="paused_limit")
    busy = card_tree(world, "aaaa0005-0", stage="cancelled")
    (world.root / "aaaa0005-0" / "turn.pid").write_text('{"pid": 1}', encoding="utf-8")
    before = sh(checkout, "git", "status", "--porcelain")

    report = prune.run(world.root, always)

    assert report["cards"] == {
        "aaaa0001-0": "removed, branch deleted",
        "aaaa0002-0": "removed, branch kept",
        "aaaa0003-0": "kept: changes",
    }
    assert int(str(report["freed_bytes"])) > 0
    assert not shipped.exists()
    assert not unpushed.exists()
    assert dirty.exists()
    assert waiting.exists()
    assert busy.exists()
    listed = branches(world)
    assert "todo/aaaa0001-0" not in listed  # its tip was on origin: nothing is lost
    assert "todo/aaaa0002-0" in listed  # the cancelled card's unpushed commit keeps its branch
    assert sh(checkout, "git", "status", "--porcelain") == before


def test_t2585_prune_stops_when_a_route_opens(world: Env) -> None:
    kuhy_repo(world, test="true")
    tree = card_tree(world, "aaaa0001-0", stage="done_manually")
    assert prune.run(world.root, lambda: False) == {"cards": {}, "freed_bytes": 0}
    assert tree.exists()


def test_t2586_rebase_moves_a_waiting_card_onto_origin(world: Env) -> None:
    checkout = kuhy_repo(world, test="true")
    tree = card_tree(world, "bbbb0001-0")
    commit(tree, "mine.txt", "card work\n", "card work")
    upstream = commit(checkout, "theirs.txt", "kuhy pushed\n", "kuhy pushed")
    sh(checkout, "git", "push", "-q", "origin", "main")
    assert rebase.run(world.root, always, NOW) == {"cards": {"bbbb0001-0": "rebased"}}
    sh(tree, "git", "merge-base", "--is-ancestor", upstream, "HEAD")
    assert (tree / "mine.txt").is_file()
    assert rebase.run(world.root, always, NOW) == {"cards": {"bbbb0001-0": "current"}}


def test_t2586_rebase_conflict_aborts_and_files_one_ticket(world: Env) -> None:
    checkout = kuhy_repo(world, test="true")
    tree = card_tree(world, "bbbb0002-0")
    head = commit(tree, "README.md", "card side\n", "card edit")
    commit(checkout, "README.md", "kuhy side\n", "kuhy edit")
    sh(checkout, "git", "push", "-q", "origin", "main")
    assert rebase.run(world.root, always, NOW) == {"cards": {"bbbb0002-0": "conflict: ticket filed"}}
    assert sh(tree, "git", "rev-parse", "HEAD").strip() == head
    assert sh(tree, "git", "status", "--porcelain") == ""
    assert [r["signature"] for r in records()] == ["nolimit-rebase"]
    rebase.run(world.root, always, NOW)
    assert [r["count"] for r in records()] == [2]  # the same conflict counts up, never files twice


def test_t2586_rebase_skips_dirty_busy_and_ended_cards(world: Env) -> None:
    kuhy_repo(world, test="true")
    dirty = card_tree(world, "bbbb0003-0")
    (dirty / "wip.txt").write_text("wip\n", encoding="utf-8")
    card_tree(world, "bbbb0004-0", stage="done_manually")
    card_tree(world, "bbbb0005-0")
    (world.root / "bbbb0005-0" / "turn.pid").write_text('{"pid": 1}', encoding="utf-8")
    assert rebase.run(world.root, always, NOW) == {"cards": {"bbbb0003-0": "skipped: changes"}}
    assert [c.id for c in cards.waiting(world.root)] == ["bbbb0003-0"]
