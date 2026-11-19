"""The wrapper refuses a whole script as the locked command; a plain script still locks each tool (T2165)."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock

if TYPE_CHECKING:
    from pathlib import Path

HINT = (
    "buildlock: refusing to hold the build lock for a whole script ({cmd}): lock each heavy command on its "
    "own (buildlock.sh flutter build apk), or run the script plainly with PATH passed on (systemd-run "
    "-E PATH -E TODOIMPL_BUILD_CARD) so each heavy tool inside takes the lock itself\n"
)


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    holder = buildlock.root() / buildlock.HOLDER
    executable(
        fakebin / "make", f'#!/bin/bash\necho "make $* held=$TODOIMPL_BUILD_LOCK_HELD by $(<{holder})"\n'
    )
    executable(tmp_path / "gate.sh", "#!/bin/bash\nmake one\nmake two\n")
    return {**os.environ, "PATH": f"{shims}:{fakebin}:{os.environ['PATH']}", buildlock.CARD_VAR: "card-s"}


def _wrap(argv: list[str], env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    return subprocess.run(
        [wrapper, *argv], env=env, cwd=cwd, capture_output=True, text=True, timeout=10, check=False
    )


@pytest.mark.parametrize(
    "argv",
    [
        ["bash", "gate.sh"],
        ["sh", "-c", "make a && make b"],
        ["zsh", "-c", "make"],
        ["bash"],
        ["python3", "-u", "build.py"],
        ["python3.15", "-c", "print(1)"],
        ["node", "build.js"],
        ["timeout", "-s", "KILL", "600", "bash", "gate.sh"],
        ["env", "A=1", "nice", "-n", "5", "bash", "gate.sh"],
        ["./gate.sh"],
    ],
)
def test_t2165_a_whole_script_as_the_locked_command_is_refused(
    env: dict[str, str], tmp_path: Path, argv: list[str]
) -> None:
    done = _wrap(argv, env, tmp_path)
    assert (done.returncode, done.stdout) == (2, "")
    assert done.stderr == HINT.format(cmd=" ".join(argv))
    assert not (buildlock.root() / buildlock.HOLDER).exists()


def test_t2165_a_script_run_plainly_locks_each_heavy_tool_on_its_own(
    env: dict[str, str], tmp_path: Path
) -> None:
    done = subprocess.run(
        ["bash", "gate.sh"], env=env, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    lines = done.stdout.splitlines()
    assert [line.partition(" since ")[0] for line in lines] == [
        "make one held=1 by card-s (make one)",
        "make two held=1 by card-s (make two)",
    ]


@pytest.mark.parametrize(
    ("argv", "out"),
    [
        (["python3", "-m", "this_module_does_not_exist_x"], ""),
        (["bash", "--version"], "GNU bash"),
        (["timeout", "5", "make", "x"], "make x held=1"),
    ],
)
def test_t2165_a_module_run_a_probe_or_a_tool_behind_a_prefix_still_runs(
    env: dict[str, str], tmp_path: Path, argv: list[str], out: str
) -> None:
    done = _wrap(argv, env, tmp_path)
    assert "refusing" not in done.stderr
    assert out in done.stdout


def test_t2165_a_nested_script_under_a_held_lock_runs_at_once(env: dict[str, str], tmp_path: Path) -> None:
    done = _wrap(["bash", "gate.sh"], {**env, buildlock.HELD_VAR: "1"}, tmp_path)
    assert done.returncode == 0
    assert done.stdout.startswith("make one held=1")
