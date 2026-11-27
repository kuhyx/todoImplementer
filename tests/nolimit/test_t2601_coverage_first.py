"""The coverage step writes the report before it reads it (T2601).

2026-11-27, first live run on kcd2-dice-solver: its `test` (`pnpm run test`) writes no `coverage/lcov.info`,
only its `coverage` command does, so `coverage-gaps` exited 2 and filed a false "unreadable report" ticket on
every visit. The repo's own `- coverage:` command now runs first; its report never reaches a commit.
"""

from __future__ import annotations

import json

import pytest
from nolimitfakes import kuhy_repo, script_steps
from runnerfakes import Env
from test_nolimit_repo_steps import GAPS, fake_tool, load, records
from todoimpl.nolimit import coverage, fixes, run, worktree

NOW = 1_800_000_000.0


@pytest.fixture(autouse=True)
def no_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])


def _gaps_tool(world: Env) -> None:
    fake_tool(world, "coverage-gaps", f"[ -f cov.xml ] || exit 2\necho '{json.dumps(GAPS)}'\nexit 1")


def test_t2601_the_coverage_command_runs_before_the_gaps_are_read(world: Env) -> None:
    _gaps_tool(world)
    kuhy_repo(world, test="true", coverage="echo data > cov.xml", coverage_gaps="coverage-gaps cov.xml")
    assert run.visit(load(world), NOW, push=False) == "green"
    signatures = [str(r["signature"]) for r in records()]
    assert len(signatures) == len(GAPS["files"])
    assert all(s.startswith("nolimit-coverage-") and s != "nolimit-coverage-gaps" for s in signatures)
    tree = worktree.Tree(world.root / "nolimit" / "demo", "nolimit", "main")
    assert not worktree.dirty(tree)  # the report is gone, so no later commit can carry it


def test_t2601_a_red_coverage_command_is_one_ticket_and_no_gaps_run(world: Env) -> None:
    _gaps_tool(world)
    kuhy_repo(world, test="true", coverage="exit 3", coverage_gaps="coverage-gaps cov.xml")
    run.visit(load(world), NOW, push=False)
    assert [r["signature"] for r in records()] == ["nolimit-coverage"]


@pytest.mark.parametrize("value", ["`n/a`", "n/a: no coverage tooling for this stack"])
def test_t2601_a_repo_without_a_coverage_command_reads_the_gates_report(world: Env, value: str) -> None:
    fake_tool(world, "coverage-gaps", "exit 0")
    kuhy_repo(world, test="true", coverage_gaps="coverage-gaps cov.xml")
    claude = world.src / "demo" / "CLAUDE.md"
    claude.write_text(claude.read_text(encoding="utf-8") + f"- coverage: {value}\n", encoding="utf-8")
    assert coverage.generate(load(world)) is None


def test_t2601_a_coverage_command_cut_at_60_s_files_a_slow_ticket(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    _gaps_tool(world)
    kuhy_repo(world, test="true", coverage="true", coverage_gaps="coverage-gaps cov.xml")
    script_steps(monkeypatch, {"coverage": None})
    assert coverage.run(load(world), world.src / "demo", NOW) == []
    assert records() == []  # no gaps read, no red ticket: the cut is a slow-step ticket
