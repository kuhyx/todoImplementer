"""T2617: a visit with a pin bump runs the suite once on autofix + bump, not once per commit (live C10)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest
from nolimitfakes import kuhy_repo, remote_log
from todoimpl.errors.sources import state_base
from todoimpl.nolimit import bump, fixes, repos, run, status

if TYPE_CHECKING:
    from pathlib import Path

    from runnerfakes import Env

NOW = 1_800_000_000.0
FRESHNESS = "scripts/check_dependency_freshness.sh"


def _signatures() -> list[object]:
    path = state_base() / "app-errors" / "nolimit.json"
    rows = json.loads(path.read_text(encoding="utf-8"))["errors"] if path.exists() else []
    return [r["signature"] for r in rows]


def _bumpable(world: Env, gate: str, log: Path, monkeypatch: pytest.MonkeyPatch) -> repos.Repo:
    script = world.home / bump.SCRIPT
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text("import pathlib\npathlib.Path('deps.txt').write_text('lib==2\\n')\n", encoding="utf-8")
    monkeypatch.setattr(fixes, "autofix", lambda _wt: [])
    monkeypatch.setattr(fixes, "setup", lambda _wt: [("setup-x", f"echo setup >> {log}")])
    files = {FRESHNESS: "exit 0\n", "deps.txt": "lib==1\n"}
    kuhy_repo(world, test=f"echo gate >> {log} && {gate}", files=files)
    found = repos.load(world.src / "demo")
    assert found is not None
    return found


def test_t2617_a_green_bump_runs_the_gate_once_after_installing_the_new_pins(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = world.tmp / "steps.log"
    assert run.visit(_bumpable(world, "true", log, monkeypatch), NOW) == status.PUSHED
    assert log.read_text(encoding="utf-8").split() == ["setup", "setup", "gate"]
    assert remote_log(world)[0] == "Bump dependency pins to the newest stable"
    assert _signatures() == []


def test_t2617_a_bump_that_turns_the_gate_red_is_dropped_and_the_base_gated_again(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = world.tmp / "steps.log"
    repo = _bumpable(world, "grep -q 'lib==1' deps.txt", log, monkeypatch)
    assert run.visit(repo, NOW) == status.GREEN  # nothing left to push
    assert log.read_text(encoding="utf-8").split() == ["setup", "setup", "gate", "setup", "gate"]
    assert remote_log(world)[0] == "commands"
    assert _signatures() == ["nolimit-bump"]


def test_t2617_a_base_that_is_red_without_the_bump_files_the_gate_not_the_bump(
    world: Env, monkeypatch: pytest.MonkeyPatch
) -> None:
    log = world.tmp / "steps.log"
    assert run.visit(_bumpable(world, "false", log, monkeypatch), NOW) == status.RED
    assert log.read_text(encoding="utf-8").split() == ["setup", "setup", "gate", "setup", "gate"]
    assert _signatures() == ["nolimit-gate"]
