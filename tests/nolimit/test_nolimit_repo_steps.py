"""The new steps of a repo visit: coverage gaps as tickets (T2584), pin bumps (T2588), warm caches (T2587)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from nolimitfakes import kuhy_repo, remote_log
from runnerfakes import Env
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import bump, coverage, fixes, repos, run, status, worktree

NOW = 1_800_000_000.0
GAPS = {
    "files": [{"path": f"src/m{i}.py", "missed_lines": "3-4", "missed_branch_count": 1} for i in range(2)]
}
FRESHNESS = "scripts/check_dependency_freshness.sh"


def records() -> list[dict[str, object]]:
    path = state_base() / "app-errors" / "nolimit.json"
    return json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []


def fake_tool(world: Env, name: str, body: str) -> None:
    tool = world.bin / name
    tool.write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    tool.chmod(0o755)


def load(world: Env, name: str = "demo") -> repos.Repo:
    found = repos.load(world.src / name)
    assert found is not None
    return found


@pytest.fixture
def no_fixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])


@pytest.mark.usefixtures("no_fixes")
def test_t2584_coverage_gaps_file_one_ticket_per_file(world: Env) -> None:
    args = world.tmp / "gaps.args"
    fake_tool(world, "coverage-gaps", f"echo \"$@\" > {args}\necho '{json.dumps(GAPS)}'\nexit 1")
    kuhy_repo(world, test="true", coverage_gaps="coverage-gaps coverage.xml")
    assert run.visit(load(world), NOW, push=False) == status.GREEN
    assert run.visit(load(world), NOW, push=False) == status.GREEN
    gaps = [r for r in records() if str(r["signature"]).startswith("nolimit-coverage-")]
    assert len(gaps) == 2  # one per file, the second visit counted up
    assert {r["count"] for r in gaps} == {2}
    assert {r["open"] for r in gaps} == {True}
    assert "src/m0.py" in str(gaps[0]["message"])
    assert "3-4" in str(gaps[0]["message"])
    assert args.read_text(encoding="utf-8").split() == ["coverage.xml", "--json", "--max-files", "10"]
    assert not (world.root / "nolimit" / "demo" / coverage.OUT).exists()  # never reaches a commit


@pytest.mark.usefixtures("no_fixes")
def test_t2584_unreadable_report_is_one_ticket_and_no_command_is_none(world: Env) -> None:
    fake_tool(world, "coverage-gaps", "exit 2")
    kuhy_repo(world, test="true", coverage_gaps="coverage-gaps coverage.xml")
    kuhy_repo(world, "plain", test="true")
    run.visit(load(world), NOW, push=False)
    assert [r["signature"] for r in records()] == ["nolimit-coverage-gaps"]
    assert coverage.command(load(world, "plain")) is None


def pins_script(world: Env, change: str) -> None:
    script = world.home / bump.SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(f"import pathlib\n{change}\n", encoding="utf-8")


@pytest.mark.usefixtures("no_fixes")
def test_t2588_a_bump_that_keeps_the_gate_green_is_pushed(world: Env) -> None:
    pins_script(world, "pathlib.Path('deps.txt').write_text('lib==2\\n')")
    kuhy_repo(world, test="true", files={FRESHNESS: "exit 0\n", "deps.txt": "lib==1\n"})
    assert run.visit(load(world), NOW) == status.PUSHED
    assert remote_log(world)[0] == "Bump dependency pins to the newest stable"


@pytest.mark.usefixtures("no_fixes")
def test_t2588_a_bump_that_turns_the_gate_red_is_dropped_with_a_ticket(world: Env) -> None:
    pins_script(world, "pathlib.Path('deps.txt').write_text('lib==2\\n')")
    kuhy_repo(world, test="grep -q 'lib==1' deps.txt", files={FRESHNESS: "exit 0\n", "deps.txt": "lib==1\n"})
    assert run.visit(load(world), NOW) == status.GREEN  # nothing left to push
    assert remote_log(world)[0] == "commands"
    assert [r["signature"] for r in records()] == ["nolimit-bump"]


@pytest.mark.usefixtures("no_fixes")
def test_t2588_no_freshness_gate_no_bump_and_a_missing_script_is_loud(world: Env) -> None:
    kuhy_repo(world, test="true")
    tree = worktree.prepare(load(world), NOW)
    assert bump.apply(load(world), tree, NOW) == bump.NONE
    kuhy_repo(world, "fresh", test="true", files={FRESHNESS: "exit 0\n"})
    tree = worktree.prepare(load(world, "fresh"), NOW)
    assert bump.apply(load(world, "fresh"), tree, NOW) == bump.FAILED
    assert "apply_dep_pins.py is missing" in str(records()[0]["detail"])


def test_t2587_setup_installs_every_lockfile_one_dir_down(tmp_path: Path) -> None:
    for rel in ("uv.lock", "app/pubspec.lock", "web/pnpm-lock.yaml", ".hidden/uv.lock"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("", encoding="utf-8")
    assert fixes.setup(tmp_path) == [
        ("setup-pnpm-web", f"cd web && {fixes.PNPM_SETUP}"),
        ("setup-uv", fixes.UV_SETUP),
        ("setup-pub-app", f"cd app && {fixes.PUB_SETUP}"),
    ]
