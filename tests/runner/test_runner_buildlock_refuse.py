"""A whole script given to the wrapper runs without the lock; each heavy tool inside locks itself (T2165)."""

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
    "buildlock: not holding the build lock for a whole script ({cmd}): it runs unlocked and each heavy tool "
    "inside takes the lock itself; lock each heavy command on its own (buildlock.sh flutter build apk), or "
    "run the script plainly with PATH passed on (systemd-run -E PATH -E TODOIMPL_BUILD_CARD)\n"
)
GATE = ["make one held=1 by card-s (make one)", "make two held=1 by card-s (make two)"]
SPAWN = "require('child_process').execSync('make n', {stdio: 'inherit'})"


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    """No shims on PATH: the wrapper must put them first itself, or the tools inside run unlocked."""
    buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    holder = buildlock.root() / buildlock.HOLDER
    executable(
        fakebin / "make",
        f'#!/bin/bash\necho "make $* held=$TODOIMPL_BUILD_LOCK_HELD by $(<{holder})" 2>/dev/null\n',
    )
    executable(tmp_path / "gate.sh", "#!/bin/bash\nmake one\nmake two\n")
    return {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", buildlock.CARD_VAR: "card-s"}


def _wrap(
    argv: list[str], env: dict[str, str], cwd: Path, stdin: str = ""
) -> subprocess.CompletedProcess[str]:
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    return subprocess.run(
        [wrapper, *argv],
        env=env,
        cwd=cwd,
        input=stdin,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def _locks(out: str) -> list[str]:
    return [line.partition(" since ")[0] for line in out.splitlines()]


@pytest.mark.parametrize(
    ("argv", "stdin", "locks"),
    [
        (["bash", "gate.sh"], "", GATE),
        (["sh", "-c", "make one && make two"], "", GATE),
        (["bash"], "make one\nmake two\n", GATE),
        (
            ["python3", "-u", "-c", "import subprocess; subprocess.run(['make', 'p'])"],
            "",
            ["make p held=1 by card-s (make p)"],
        ),
        (["node", "-e", SPAWN], "", ["make n held=1 by card-s (make n)"]),
        (["timeout", "-s", "KILL", "600", "bash", "gate.sh"], "", GATE),
        (["env", "A=1", "nice", "-n", "5", "bash", "gate.sh"], "", GATE),
        (["./gate.sh"], "", GATE),
    ],
)
def test_t2165_a_whole_script_runs_unlocked_and_each_tool_inside_locks_itself(
    env: dict[str, str], tmp_path: Path, argv: list[str], stdin: str, locks: list[str]
) -> None:
    done = _wrap(argv, env, tmp_path, stdin)
    assert done.returncode == 0, done.stderr
    assert _locks(done.stdout) == locks  # the script itself never held the lock: each make did, on its own
    assert done.stderr == HINT.format(cmd=" ".join(argv))


def test_t2165_the_scripts_exit_code_comes_back(env: dict[str, str], tmp_path: Path) -> None:
    done = _wrap(["sh", "-c", "exit 3"], env, tmp_path)
    assert (done.returncode, done.stdout) == (3, "")
    assert not (buildlock.root() / buildlock.HOLDER).exists()


def test_t2165_a_script_run_plainly_locks_each_heavy_tool_on_its_own(
    env: dict[str, str], tmp_path: Path
) -> None:
    shims = buildlock.root() / buildlock.SHIM_DIR
    plain = {**env, "PATH": f"{shims}:{env['PATH']}"}
    done = subprocess.run(
        ["bash", "gate.sh"], env=plain, cwd=tmp_path, capture_output=True, text=True, check=False
    )
    assert _locks(done.stdout) == GATE


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
    assert "whole script" not in done.stderr
    assert out in done.stdout


def test_t2165_a_nested_script_under_a_held_lock_runs_at_once(env: dict[str, str], tmp_path: Path) -> None:
    done = _wrap(["bash", "gate.sh"], {**env, buildlock.HELD_VAR: "1"}, tmp_path)
    assert done.returncode == 0
    assert done.stdout.startswith("make one held=1")
    assert "whole script" not in done.stderr
