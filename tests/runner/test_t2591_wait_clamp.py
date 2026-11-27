"""A session's wait never runs past 40 s (T2591, `waitshim.sh`).

2026-11-27: card 5ad97967-0 ran `timeout 2400 tail --pid=$(systemctl --user show -p MainPID ...) -f /dev/null`
and `timeout 3000 ...` against the standing prompt's 40 s rule; each call sat quiet over 60 s and filed
`stall-job-tail`. Earlier d3142f69-0 followed a log (`tail -n0 -F log`), which never ends. The `timeout` and
`tail` shims now cap every wait at 40 s, so the prompt rule no longer depends on the model obeying it.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from todoimpl.runner import buildlock

ECHO = '#!/bin/bash\nprintf "%s\\n" "$(basename "$0")" "$@"\n'


@pytest.fixture
def shim(tmp_path: Path) -> tuple[Path, Path]:
    """Return the board's shim dir plus fake real `timeout` and `tail` that print their name and argv."""
    shims = buildlock.ensure(tmp_path / "root")
    real = tmp_path / "bin"
    real.mkdir()
    for name in ("timeout", "tail"):
        (real / name).write_text(ECHO, encoding="utf-8")
        (real / name).chmod(0o755)
    return shims, real


def _run(shim: tuple[Path, Path], tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    shims, real = shim
    env = {"PATH": f"{shims}:{real}:/usr/bin:/bin", "HOME": os.environ["HOME"]}
    return subprocess.run([str(shims / tool), *args], env=env, capture_output=True, text=True, check=True)


def test_t2591_a_long_timeout_on_a_job_wait_is_cut_to_40_s(shim: tuple[Path, Path]) -> None:
    done = _run(shim, "timeout", "2400", "tail", "--pid=7", "-f", "/dev/null")
    assert done.stdout.splitlines() == ["timeout", "40", "tail", "--pid=7", "-f", "/dev/null"]
    assert "40 s" in done.stderr


@pytest.mark.parametrize(
    ("args", "want"),
    [
        (
            ["-k", "5", "3000", "inotifywait", "-e", "close", "x"],
            ["-k", "5", "40", "inotifywait", "-e", "close", "x"],
        ),
        (["5m", "gh", "run", "watch", "1"], ["40", "gh", "run", "watch", "1"]),
        (["--signal=KILL", "1h", "sleep", "900"], ["--signal=KILL", "40", "sleep", "900"]),
        (
            ["-s", "TERM", "90s", "/usr/bin/tail", "-f", "log"],
            ["-s", "TERM", "40", "/usr/bin/tail", "-f", "log"],
        ),
    ],
)
def test_t2591_every_waiter_and_duration_form_is_cut(
    shim: tuple[Path, Path], args: list[str], want: list[str]
) -> None:
    assert _run(shim, "timeout", *args).stdout.splitlines() == ["timeout", *want]


@pytest.mark.parametrize(
    "args",
    [
        ["40", "tail", "--pid=7", "-f", "/dev/null"],
        ["30s", "inotifywait", "x"],
        ["55", "make", "test-shard", "SHARD=1"],
        ["600", "bash", "-c", "pytest"],
    ],
)
def test_t2591_short_waits_and_non_waits_pass_through(shim: tuple[Path, Path], args: list[str]) -> None:
    done = _run(shim, "timeout", *args)
    assert done.stdout.splitlines() == ["timeout", *args]
    assert done.stderr == ""


@pytest.mark.parametrize(
    "args",
    [
        ["-n0", "-F", "log"],
        ["-f", "log"],
        ["--follow=name", "log"],
        ["-fn5", "log"],
        ["-n", "5", "-F", "log"],
    ],
)
def test_t2591_following_a_file_ends_after_40_s(shim: tuple[Path, Path], args: list[str]) -> None:
    real = shim[1]
    done = _run(shim, "tail", *args)
    assert done.stdout.splitlines() == ["timeout", "40", str(real / "tail"), *args]
    assert "40 s" in done.stderr


@pytest.mark.parametrize("args", [["-n", "5", "log"], ["-n", "+3", "log"], ["-c", "100", "log"], ["log"]])
def test_t2591_plain_tail_passes_through(shim: tuple[Path, Path], args: list[str]) -> None:
    done = _run(shim, "tail", *args)
    assert done.stdout.splitlines() == ["tail", *args]
    assert done.stderr == ""
