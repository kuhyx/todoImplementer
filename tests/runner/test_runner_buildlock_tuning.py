"""Build shims bound a build's cost: `fvm` locks like `flutter`, tests run 4 wide, builds run at nice 19."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock

if TYPE_CHECKING:
    from pathlib import Path

# A fake tool: logs its argv, whether it holds the build lock, and its niceness.
PROBE = (
    '#!/bin/bash\nprintf "%s|held=%s|nice=%s\\n" "$*" "${TODOIMPL_BUILD_LOCK_HELD:-0}" "$(nice)"'
    ' >> "$PROBE_LOG"\n'
)


@pytest.fixture
def probe(tmp_path: Path) -> tuple[Path, Path]:
    """Return the shim dir and the log the fake tools append to."""
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    for tool in ("flutter", "fvm", "cargo"):
        executable(fakebin / tool, PROBE)
    return shims, tmp_path / "probe.log"


def _run(probe: tuple[Path, Path], *argv: str) -> str:
    shims, log = probe
    path = f"{shims}:{log.parent / 'fakebin'}:{os.environ['PATH']}"
    env = {**os.environ, "PATH": path, buildlock.CARD_VAR: "c", "PROBE_LOG": str(log)}
    subprocess.run(argv, env=env, check=True, capture_output=True, timeout=30)
    return log.read_text().strip()


def test_t2488_fvm_flutter_runs_under_the_build_lock(probe: tuple[Path, Path]) -> None:
    assert (probe[0] / "fvm").exists()
    assert "held=1" in _run(probe, "fvm", "flutter", "build", "apk")


@pytest.mark.parametrize("argv", [("flutter", "test"), ("fvm", "flutter", "test")])
def test_t2489_flutter_test_without_a_width_runs_four_wide(
    probe: tuple[Path, Path], argv: tuple[str, ...]
) -> None:
    assert (
        _run(probe, *argv, "test/a_test.dart").split("|")[0].endswith("test --concurrency=4 test/a_test.dart")
    )


@pytest.mark.parametrize("flag", ["-j2", "--concurrency=8", "--concurrency", "-j"])
def test_t2489_an_explicit_width_stays(probe: tuple[Path, Path], flag: str) -> None:
    out = _run(probe, "flutter", "test", flag, "3")
    assert "--concurrency=4" not in out
    assert out.startswith(f"test {flag} 3|")


def test_t2489_other_flutter_commands_are_untouched(probe: tuple[Path, Path]) -> None:
    assert _run(probe, "flutter", "build", "apk").startswith("build apk|")


def test_t2490_a_build_runs_at_the_lowest_priority(probe: tuple[Path, Path]) -> None:
    assert _run(probe, "cargo", "build").endswith("|nice=19")
