"""Edges of a repo visit: failing or cut bump steps, bad coverage reports, a route that opens."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nolimitfakes import kuhy_repo, script_steps
from runnerfakes import Env, sh
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import bump, coverage, fixes, repos, run, status, steps, tick, trigger, worktree

NOW = 1_800_000_000.0
FRESHNESS = "scripts/check_dependency_freshness.sh"
PINS = "pathlib.Path('deps.txt').write_text('lib==2\\n')"


def records(name: str = "nolimit.json") -> list[dict[str, object]]:
    path = state_base() / "app-errors" / name
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


def load(world: Env, name: str = "demo") -> repos.Repo:
    found = repos.load(world.src / name)
    assert found is not None
    return found


def bumpable(world: Env, change: str = PINS) -> tuple[repos.Repo, worktree.Tree]:
    """Make a repo with the freshness gate and the pins script; return it and its prepared tree."""
    script = world.home / bump.SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f"import pathlib\n{change}\n", encoding="utf-8")
    kuhy_repo(world, test="true", files={FRESHNESS: "exit 0\n", "deps.txt": "lib==1\n"})
    repo = load(world)
    return repo, worktree.prepare(repo, NOW)


def test_a_bump_script_cut_at_60_s_files_a_slow_ticket_and_fails(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, tree = bumpable(world)
    script_steps(monkeypatch, {"bump": None})
    assert bump.run(repo, tree, "true", NOW) == bump.FAILED
    assert [r["signature"] for r in records("slow-steps.json")] == ["slow-nolimit-bump"]


def test_a_bump_commit_that_fails_drops_the_pins_and_files_a_ticket(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    repo, tree = bumpable(world)
    script_steps(monkeypatch, {"bump-commit": 1})
    assert bump.run(repo, tree, "true", NOW) == bump.FAILED
    assert (tree.path / "deps.txt").read_text(encoding="utf-8") == "lib==1\n"
    assert [r["signature"] for r in records()] == ["nolimit-bump-commit"]


def test_a_regate_cut_at_60_s_drops_the_bump_commit(world: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    repo, tree = bumpable(world)
    script_steps(monkeypatch, {"bump-gate": None})
    assert bump.run(repo, tree, "true", NOW) == bump.SLOW
    assert sh(tree.path, "git", "log", "-1", "--format=%s").strip() == "commands"
    assert [r["signature"] for r in records("slow-steps.json")] == ["slow-nolimit-bump-gate"]


def test_a_bump_that_changes_nothing_is_none(world: Env) -> None:
    repo, tree = bumpable(world, "pass")
    assert bump.run(repo, tree, "true", NOW) == bump.NONE
    assert records() == []


def test_an_unreadable_or_missing_gaps_report_is_empty_and_removed(tmp_path: Path) -> None:
    assert coverage.gaps(tmp_path) == []  # no report written
    (tmp_path / coverage.OUT).write_text("{not json", encoding="utf-8")
    assert coverage.gaps(tmp_path) == []
    assert not (tmp_path / coverage.OUT).exists()


def test_a_coverage_gaps_step_cut_at_60_s_files_a_slow_ticket(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    kuhy_repo(world, test="true", coverage_gaps="coverage-gaps coverage.xml")
    script_steps(monkeypatch, {"coverage-gaps": None})
    assert coverage.run(load(world), world.src / "demo", NOW) == []
    assert [r["signature"] for r in records("slow-steps.json")] == ["slow-nolimit-coverage-gaps"]


def test_a_route_that_opens_after_the_gate_skips_the_bump(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])
    ran: list[str] = []
    real = steps.run

    def spy(name: str, command: str, cwd: Path, *rest: object) -> steps.Step:
        ran.append(name)
        return real(name, command, cwd)

    monkeypatch.setattr(steps, "run", spy)
    kuhy_repo(world, test="true", files={FRESHNESS: "exit 0\n"})
    assert run.visit(load(world), NOW, lambda: "gate" not in ran, push=False) == status.GREEN
    assert "bump" not in ran


def test_the_chore_is_skipped_when_a_route_opens_during_the_visit(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([True, False])
    monkeypatch.setattr(trigger, "holds", lambda _root, _now, _up=None: next(answers))
    assert tick.tick(world.root) is None
    assert "chores" not in status.load(world.root)
