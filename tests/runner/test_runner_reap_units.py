"""A resting run's cleanup stops the user units that run from its worktrees (T2494), via a fake systemctl."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from runnerfakes import Env
from todoimpl.board import state as store
from todoimpl.runner import reap, units

# The fake answers `list-units` and `show` from files beside it and logs every call.
FAKE = """#!/bin/sh
d=$(dirname "$0")
echo "$*" >> "$d/calls"
case "$*" in
  *list-units*) cat "$d/units" ;;
  *show*) cat "$d/show" ;;
  *stop*) exit "$(cat "$d/stop-exit" 2>/dev/null || echo 0)" ;;
esac
"""


def fake(tmp: Path, monkeypatch: pytest.MonkeyPatch, dirs: dict[str, str]) -> Path:
    """Install the fake systemctl; `dirs` maps each active unit to its WorkingDirectory ("" for none)."""
    bin_dir = tmp / "fake-systemctl"
    bin_dir.mkdir()
    tool = bin_dir / "systemctl"
    tool.write_text(FAKE, encoding="utf-8")
    tool.chmod(0o755)
    (bin_dir / "units").write_text("".join(f"{u} loaded active running x\n" for u in dirs), encoding="utf-8")
    blocks = [f"Id={u}\nWorkingDirectory={d}\n" for u, d in dirs.items()]
    (bin_dir / "show").write_text("\n".join(blocks), encoding="utf-8")
    monkeypatch.setenv(units.ENV, str(tool))
    return bin_dir


def calls(bin_dir: Path) -> list[str]:
    log = bin_dir / "calls"
    return log.read_text(encoding="utf-8").splitlines() if log.exists() else []


def run_dir(world: Env, stage: str = "shipped") -> Path:
    d = world.root / "abcd1234-0"
    d.mkdir(parents=True)
    store.save(d, store.RunState(task_id="abcd1234-0", stage=stage))
    return d


@pytest.fixture
def setup(world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    run = run_dir(world)
    (run / "logs").mkdir()
    bin_dir = fake(
        tmp_path,
        monkeypatch,
        {
            "tutor51-web.service": f"{run}/wt",  # its worktree is already gone
            "web.service": f"!{run}/wt-utils/web",
            "logs.service": f"{run}/logs",
            "other-run.service": f"{world.root}/ffff0000-0/wt",
            "todoimplementer.service": "/home/someone/src/todoImplementer",
            "bare.service": "",
        },
    )
    monkeypatch.setattr(reap, "live_cwds", list)
    return run, bin_dir


def test_t2494_cleanup_stops_units_that_run_from_its_worktrees(setup: tuple[Path, Path]) -> None:
    run, bin_dir = setup
    rep = reap.clean(run, apply=True)
    assert rep.refused == ""
    assert rep.units == ["tutor51-web.service", "web.service"]
    assert calls(bin_dir)[-1] == "--user stop -- tutor51-web.service web.service"


def test_t2494_a_dry_run_lists_them_and_stops_nothing(setup: tuple[Path, Path]) -> None:
    run, bin_dir = setup
    assert reap.clean(run, apply=False).units == ["tutor51-web.service", "web.service"]
    assert not any("stop" in c for c in calls(bin_dir))


def test_t2494_a_run_that_is_not_resting_stops_nothing(
    world: Env, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    run = run_dir(world, stage="implement")
    bin_dir = fake(tmp_path, monkeypatch, {"tutor51-web.service": f"{run}/wt"})
    assert reap.clean(run, apply=True).refused == "stage implement"
    assert calls(bin_dir) == []


def test_t2494_the_unit_stops_before_the_live_cwd_check(
    setup: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The unit's own process works in the worktree; once it is stopped the run may be cleaned."""
    run, bin_dir = setup
    monkeypatch.setattr(
        reap, "live_cwds", lambda: [] if any("stop" in c for c in calls(bin_dir)) else [run / "wt"]
    )
    assert reap.clean(run, apply=False).refused == "a live process works in it"  # a dry run stops nothing
    assert reap.clean(run, apply=True).refused == ""


def test_t2494_a_failing_or_missing_systemctl_never_blocks_the_cleanup(
    setup: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    run, bin_dir = setup
    (bin_dir / "stop-exit").write_text("1", encoding="utf-8")
    assert reap.clean(run, apply=True).units == ["tutor51-web.service", "web.service"]
    (bin_dir / "units").write_text("", encoding="utf-8")
    assert units.in_worktrees(run) == []
    monkeypatch.setenv(units.ENV, str(bin_dir / "missing"))
    assert units.in_worktrees(run) == []
    units.stop(["x.service"])
    monkeypatch.delenv(units.ENV)
    assert os.environ.get(units.ENV) is None
    assert units.tool() == "systemctl"
