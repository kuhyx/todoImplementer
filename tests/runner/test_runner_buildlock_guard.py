"""Sessions never touch the build lock by hand: the prompt says so and a `flock` shim refuses it (T2167)."""

from __future__ import annotations

import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from todoimpl.prompts.standing import GRANT
from todoimpl.runner import buildlock

if TYPE_CHECKING:
    from pathlib import Path

REFUSED = (
    "buildlock: refusing flock on the board's build lock: it serves builds in arrival order, so run each "
    "heavy command plainly (the shims queue it) or as buildlock.sh <tool> [args...]; see the queue with "
    "buildlock.sh --queue\n"
)


@pytest.fixture
def env() -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    return {**os.environ, "PATH": f"{shims}:{os.environ['PATH']}"}


def _bash(script: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script], env=env, cwd=cwd, capture_output=True, text=True, timeout=10, check=False
    )


def test_t2167_the_standing_prompt_forbids_touching_the_lock_by_hand() -> None:
    assert "never touch build.lock, its holder file or build.queue by hand" in GRANT
    assert "never poll it with `flock -n`" in GRANT
    assert "never lock a whole script" in GRANT


@pytest.mark.parametrize(
    "script",
    [
        'exec 9>>"$ROOT/build.lock"; flock -n 9 && echo got',
        'exec 9>>"$ROOT/build.lock"; flock -x 9 && echo got',
        'cd "$ROOT" && flock -w 5 build.lock -c "echo got"',
        'flock "$ROOT/build.lock.holder" echo got',
        'flock "$ROOT/build.queue.lock" echo got',
    ],
)
def test_t2167_a_flock_on_the_build_lock_is_refused(env: dict[str, str], tmp_path: Path, script: str) -> None:
    done = _bash(script, {**env, "ROOT": str(buildlock.root())}, tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (2, "", REFUSED)


def test_t2167_flock_on_any_other_file_still_works(env: dict[str, str], tmp_path: Path) -> None:
    done = _bash(
        f'exec 9>>"{tmp_path}/mine.lock"; flock -n 9 && flock -w 1 "{tmp_path}/b" echo got', env, tmp_path
    )
    assert (done.returncode, done.stdout) == (0, "got\n")
