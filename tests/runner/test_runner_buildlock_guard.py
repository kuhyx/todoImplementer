"""Sessions never jump the build-lock queue by hand: the prompt says so, a `flock` shim queues it (T2167)."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from todoimpl.prompts.standing import GRANT
from todoimpl.runner import bgwait, buildlock, buildqueue

if TYPE_CHECKING:
    from collections.abc import Callable

REFUSED = (
    "buildlock: refusing flock on the build lock's holder or queue files: run each heavy command plainly "
    "(the shims queue it) or as buildlock.sh <tool> [args...]; see the queue with buildlock.sh --queue\n"
)
GATED = (
    '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\n'
    'while [[ -n "${GO_FILE:-}" && ! -e "$GO_FILE" ]]; do sleep 0.02; done\n'
)
# kuhy's phone_deploy (board_lock_first) holds the lock by hand for a whole deploy, this way.
BY_HAND = 'exec 8>>"$ROOT/build.lock"; flock -n 8 || flock 8 || exit 9; echo "start hand" >> "$BUILD_LOG"'


@pytest.fixture
def env(tmp_path: Path) -> dict[str, str]:
    shims = buildlock.ensure(buildlock.root())
    fakebin = tmp_path / "fakebin"
    fakebin.mkdir()
    (fakebin / "cargo").write_text(GATED)
    (fakebin / "cargo").chmod(0o755)
    path = f"{shims}:{fakebin}:{os.environ['PATH']}"
    return {**os.environ, "PATH": path, "ROOT": str(buildlock.root()), "BUILD_LOG": str(tmp_path / "log")}


def _starts(env: dict[str, str]) -> list[str]:
    path = Path(env["BUILD_LOG"])
    return path.read_text().splitlines() if path.exists() else []


def _until(check: Callable[[], bool], what: str) -> None:
    deadline = time.monotonic() + 15
    while not check():
        assert time.monotonic() < deadline, f"{what} never happened"
        time.sleep(0.02)


def _bash(script: str, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", script], env=env, cwd=cwd, capture_output=True, text=True, timeout=10, check=False
    )


def _queued(proc: subprocess.Popen[bytes]) -> bool:
    """Say whether `proc` holds its `wait` ticket: one pid per waiter, never its flock child too (T2499)."""
    return proc.pid in bgwait.queued(buildlock.root())


def test_t2167_the_standing_prompt_forbids_touching_the_lock_by_hand() -> None:
    assert "never touch build.lock, its holder file or build.queue by hand" in GRANT
    assert "never poll it with `flock -n`" in GRANT
    assert "never lock a whole script" in GRANT


def test_t2167_a_lock_held_by_hand_waits_its_turn_in_the_queue(env: dict[str, str], tmp_path: Path) -> None:
    go = tmp_path / "go"
    holder = subprocess.Popen(["cargo", "H"], env={**env, "GO_FILE": str(go)})
    _until(lambda: _starts(env) == ["start H"], "start H")
    waiter = subprocess.Popen(["cargo", "W"], env=env)
    _until(lambda: _queued(waiter), "W queueing")
    busy = _bash('exec 9>>"$ROOT/build.lock"; flock -n 9', env, tmp_path)
    assert busy.returncode == 1  # a poll never jumps the queue
    hand = subprocess.Popen(["bash", "-c", BY_HAND], env=env)
    time.sleep(0.3)
    go.touch()
    assert (holder.wait(timeout=20), waiter.wait(timeout=20), hand.wait(timeout=20)) == (0, 0, 0)
    assert _starts(env) == ["start H", "start W", "start hand"]


@pytest.mark.parametrize(
    "script",
    ['flock "$ROOT/build.lock.holder" echo got', 'cd "$ROOT" && flock -n build.queue.lock -c "echo got"'],
)
def test_t2167_a_flock_on_the_holder_or_the_queue_is_refused(
    env: dict[str, str], tmp_path: Path, script: str
) -> None:
    done = _bash(script, env, tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (2, "", REFUSED)


@pytest.mark.parametrize(
    ("script", "extra"),
    [
        ('exec 8>>"$ROOT/build.lock"; flock 8 && echo got', {}),
        ('cd "$ROOT" && flock -w 5 build.lock -c "echo got"', {}),
        ('exec 9>>"$ROOT/build.lock"; flock -n 9 && flock -u 9 && echo got', {}),
        ('exec 9>>"$ROOT/build.lock"; flock -n 9 && echo got', {buildlock.HELD_VAR: "1"}),
    ],
)
def test_t2167_a_free_lock_taken_by_hand_still_works(
    env: dict[str, str], tmp_path: Path, script: str, extra: dict[str, str]
) -> None:
    done = _bash(script, {**env, **extra}, tmp_path)
    assert (done.returncode, done.stdout, done.stderr) == (0, "got\n", "")
    assert buildqueue.tickets(buildlock.root()) == []


def test_t2167_flock_on_any_other_file_still_works(env: dict[str, str], tmp_path: Path) -> None:
    done = _bash(
        f'exec 9>>"{tmp_path}/mine.lock"; flock -n 9 && flock -w 1 "{tmp_path}/b" echo got', env, tmp_path
    )
    assert (done.returncode, done.stdout) == (0, "got\n")


def test_t2391_a_shim_of_another_build_root_later_on_path_is_never_the_real_tool(
    env: dict[str, str], tmp_path: Path
) -> None:
    other = tmp_path / "board"  # the live board's root: its flock shim would queue on its real, busy lock
    (other / "shims").mkdir(parents=True)
    (other / "buildlock.sh").write_text("#!/bin/bash\nexit 97\n")
    (other / "shims" / "flock").write_text("#!/bin/bash\nexit 97\n")
    (other / "shims" / "flock").chmod(0o755)
    shims, rest = env["PATH"].split(":", 1)
    env = {**env, "PATH": f"{shims}:{other / 'shims'}:{rest}"}
    done = _bash(f'exec 9>>"{tmp_path}/mine.lock"; flock -n 9 && echo got', env, tmp_path)
    assert (done.returncode, done.stdout) == (0, "got\n")
