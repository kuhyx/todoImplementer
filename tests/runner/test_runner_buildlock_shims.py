"""The build-lock shims: one build at a time, nested tools straight through, probes and dev servers free."""

from __future__ import annotations

import contextlib
import fcntl
import os
import subprocess
import time
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

# A fake build: logs its start and end around a short sleep, so two runs that overlap show it in the log.
SLOW = '#!/bin/bash\necho "start $1" >> "$BUILD_LOG"\nsleep 0.6\necho "end $1" >> "$BUILD_LOG"\n'


@pytest.fixture
def shims(tmp_path: Path) -> Path:
    return buildlock.ensure(buildlock.root())


@pytest.fixture
def fakebin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    return bin_dir


def _env(shims: Path, fakebin: Path, card: str, log: Path) -> dict[str, str]:
    path = f"{shims}:{fakebin}:{os.environ['PATH']}"
    return {**os.environ, "PATH": path, buildlock.CARD_VAR: card, "BUILD_LOG": str(log)}


def _start(argv: list[str], env: dict[str, str]) -> subprocess.Popen[str]:
    return subprocess.Popen(argv, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def _wait_for(log: Path, line: str) -> None:
    deadline = time.monotonic() + 10
    while line not in (log.read_text() if log.exists() else ""):
        assert time.monotonic() < deadline, f"{line!r} never logged"
        time.sleep(0.02)


@contextlib.contextmanager
def _locked() -> Iterator[None]:
    """Hold the build lock from the test itself, as another build would."""
    base = buildlock.root()
    with (base / buildlock.LOCK).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def test_t1983_two_shims_racing_never_overlap(shims: Path, fakebin: Path, tmp_path: Path) -> None:
    executable(fakebin / "cargo", SLOW)
    log = tmp_path / "builds.log"
    first = _start(["cargo", "A"], _env(shims, fakebin, "card-a", log))
    _wait_for(log, "start A")
    second = _start(["cargo", "B"], _env(shims, fakebin, "card-b", log))
    _, err_b = second.communicate(timeout=20)
    first.communicate(timeout=20)
    assert (first.returncode, second.returncode) == (0, 0)
    assert log.read_text().splitlines() == ["start A", "end A", "start B", "end B"]
    assert err_b.count("waiting for build lock held by card-a (cargo A) since ") == 1
    assert (buildlock.root() / buildlock.HOLDER).read_text() == ""


def test_t1984_nested_shims_under_a_held_lock_do_not_deadlock(
    shims: Path, fakebin: Path, tmp_path: Path
) -> None:
    executable(fakebin / "flutter", '#!/bin/bash\nexec gradle "$@"\n')
    executable(fakebin / "gradle", '#!/bin/bash\nexec java -jar "$@"\n')
    executable(fakebin / "java", '#!/bin/bash\necho "java $* held=$TODOIMPL_BUILD_LOCK_HELD"\n')
    env = _env(shims, fakebin, "card-n", tmp_path / "log")
    done = subprocess.run(
        ["flutter", "build"], env=env, capture_output=True, text=True, timeout=10, check=False
    )
    assert done.returncode == 0, done.stderr
    assert done.stdout == "java -jar build held=1\n"


@pytest.mark.parametrize(
    "args",
    [["--version"], ["help"], ["-version"], ["run", "dev"], ["preview", "--port", "1"], ["mcp-server"]],
)
def test_probes_and_dev_servers_skip_the_lock(
    shims: Path, fakebin: Path, tmp_path: Path, args: list[str]
) -> None:
    executable(fakebin / "pnpm", '#!/bin/bash\necho "pnpm $* held=${TODOIMPL_BUILD_LOCK_HELD:-}"\n')
    env = _env(shims, fakebin, "card-p", tmp_path / "log")
    with _locked():
        done = subprocess.run(
            ["pnpm", *args], env=env, capture_output=True, text=True, timeout=5, check=False
        )
    assert done.stdout == f"pnpm {' '.join(args)} held=\n"


def test_exit_code_passes_through_and_the_lock_fd_stays_with_the_wrapper(
    shims: Path, fakebin: Path, tmp_path: Path
) -> None:
    executable(fakebin / "cargo", "#!/bin/bash\n[[ -e /proc/self/fd/9 ]] && echo leaked\nexit 3\n")
    env = _env(shims, fakebin, "card-c", tmp_path / "log")
    done = subprocess.run(["cargo", "build"], env=env, capture_output=True, text=True, timeout=5, check=False)
    assert (done.returncode, done.stdout) == (3, "")


def test_a_shim_dir_listed_twice_never_loops(shims: Path, fakebin: Path, tmp_path: Path) -> None:
    alias = tmp_path / "alias"
    alias.symlink_to(shims)
    executable(fakebin / "go", "#!/bin/bash\necho real go\n")
    env = _env(shims, fakebin, "card-g", tmp_path / "log")
    env["PATH"] = f"{shims}:{alias}:{fakebin}:{os.environ['PATH']}"
    done = subprocess.run(["go", "test"], env=env, capture_output=True, text=True, timeout=5, check=False)
    assert done.stdout == "real go\n"


def test_missing_tool_and_no_tool_fail_loudly(shims: Path, tmp_path: Path) -> None:
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    missing = subprocess.run(
        [wrapper, "no-such-tool-x"], capture_output=True, text=True, timeout=5, check=False
    )
    assert (missing.returncode, missing.stderr) == (127, "buildlock: no-such-tool-x not found on PATH\n")
    bare = subprocess.run([wrapper], capture_output=True, text=True, timeout=5, check=False)
    assert bare.returncode == 2
