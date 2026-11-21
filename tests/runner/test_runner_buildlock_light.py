"""Light commands skip the build lock: `make` is no shim and `uv run <linter>` runs at once (T2415)."""

from __future__ import annotations

import fcntl
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock, lanes

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path


@pytest.fixture
def busy(tmp_path: Path) -> Iterator[dict[str, str]]:
    """Another card holds the build lock for the whole test; a fake uv echoes whether it got the lock."""
    base = buildlock.root()
    buildlock.ensure(base)
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for tool in ("uv", "flutter", "dart"):
        executable(fakebin / tool, f'#!/bin/bash\necho "{tool} $* held=${{TODOIMPL_BUILD_LOCK_HELD:-0}}"\n')
    (base / buildlock.HOLDER).write_text("card-x (godot --import) since 12:00")
    with (base / buildlock.LOCK).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", buildlock.CARD_VAR: "card-s"}


def _wrap(argv: list[str], env: dict[str, str], timeout: float) -> subprocess.CompletedProcess[str]:
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    return subprocess.run(
        [wrapper, *argv], env=env, capture_output=True, text=True, timeout=timeout, check=False
    )


def test_t2415_make_is_no_shim_and_a_stale_make_shim_is_removed(tmp_path: Path) -> None:
    shims = tmp_path / buildlock.SHIM_DIR
    shims.mkdir()
    (shims / "make").write_text("#!/bin/bash\n")
    buildlock.ensure(tmp_path)
    assert "make" not in buildlock.TOOLS
    assert not (shims / "make").exists()


@pytest.mark.parametrize(
    "argv",
    [
        ["uv", "run", "ruff", "check", "."],
        ["uv", "run", "--frozen", "ruff", "format", "--check", "."],
        ["uv", "run", "--with", "x", "--project", "p", "mypy", "server"],
        ["uv", "run", "-p", "3.15", "--directory", "d", "shellcheck", "a.sh"],
        ["flutter", "analyze", "--fatal-infos"],
        ["dart", "analyze"],
    ],
)
def test_t2415_uv_run_of_a_linter_skips_a_busy_build_lock(busy: dict[str, str], argv: list[str]) -> None:
    done = _wrap(argv, busy, 5)
    assert done.returncode == 0
    assert done.stdout == f"{' '.join(argv)} held=0\n"
    assert "waiting" not in done.stderr


@pytest.mark.parametrize(
    "argv",
    [
        ["uv", "run", "env", "pytest"],
        ["uv", "run", "--with", "ruff", "pytest"],
        ["uv", "sync"],
        ["uv", "run", "bash", "x.sh"],
        ["flutter", "test"],
        ["dart", "run", "analyze"],
    ],
)
def test_t2415_other_uv_commands_still_wait_for_the_lock(busy: dict[str, str], argv: list[str]) -> None:
    with pytest.raises(subprocess.TimeoutExpired):
        _wrap(argv, busy, 1.5)


def test_t2415_the_wrapper_and_the_lanes_share_one_linter_list() -> None:
    text = (buildlock.ensure(buildlock.root()).parent / buildlock.WRAPPER).read_text()
    line = next(ln for ln in text.splitlines() if ln.startswith("readonly LINTERS="))
    assert line.startswith(f'readonly LINTERS=" {" ".join(sorted(buildlock.LINTERS))} " #')
    assert buildlock.LINTERS <= lanes.LIGHT_TOOLS


def test_t2423_coverage_combine_and_report_skip_a_busy_build_lock(busy: dict[str, str]) -> None:
    """`make test-cov` ran `capped.sh uv run coverage combine`: it queued inside the 60 s scope (killed)."""
    combine = ["uv", "run", "--frozen", "coverage", "combine", "-q"]
    for argv in (combine, ["uv", "run", "coverage", "report"]):
        done = _wrap(argv, busy, 5)
        assert done.returncode == 0
        assert "waiting" not in done.stderr
