"""Dev servers and emulators never hold the build lock; a holder with no card is named by its repo (T2516)."""

from __future__ import annotations

import fcntl
import os
import subprocess
from typing import TYPE_CHECKING

import pytest
from runnerfakes import executable
from todoimpl.runner import buildlock, buildqueue, holdceiling

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

JAR = "/home/u/.cache/firebase/emulators/cloud-firestore-emulator-v1.19.7.jar"


@pytest.fixture
def fakebin(tmp_path: Path) -> Path:
    """Fake pnpm, npm, vite and java that print their words and whether they got the lock."""
    found = tmp_path / "fakebin"
    found.mkdir()
    for tool in ("pnpm", "npm", "vite", "java", "cargo"):
        held = "${TODOIMPL_BUILD_LOCK_HELD:-0}"
        executable(found / tool, f'#!/bin/bash\necho "{tool}${{*:+ $*}} held={held}"\n')
    return found


@pytest.fixture
def busy(fakebin: Path) -> Iterator[dict[str, str]]:
    """Another build holds the one slot for the whole test."""
    base = buildlock.root()
    buildlock.ensure(base)
    (base / buildlock.HOLDER).write_text("card-x (godot --import) since 12:00")
    with (base / buildlock.LOCK).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield {**os.environ, "PATH": f"{fakebin}:{os.environ['PATH']}", buildlock.CARD_VAR: "card-s"}


def _wrap(argv: list[str], env: dict[str, str], timeout: float, cwd: Path | None = None) -> str:
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    done = subprocess.run(
        [wrapper, *argv], env=env, capture_output=True, text=True, timeout=timeout, check=False, cwd=cwd
    )
    assert done.returncode == 0, done.stderr
    assert "waiting" not in done.stderr
    return done.stdout


@pytest.mark.parametrize(
    "argv",
    [
        ["pnpm", "exec", "astro", "dev"],
        ["pnpm", "astro", "dev", "--port", "4321"],
        ["pnpm", "exec", "vite"],
        ["pnpm", "exec", "vite", "--host"],
        ["npm", "exec", "--", "astro", "dev"],
        ["pnpm", "dlx", "wrangler", "dev"],
        ["vite"],
        ["vite", "--port", "5173"],
        ["java", "-Duser.language=en", "-jar", JAR, "--host", "127.0.0.1"],
        ["java", "-jar", "/x/firebase-database-emulator-v4.11.2.jar"],
        ["pnpm", "exec", "firebase", "emulators:start"],
    ],
)
def test_t2516_dev_servers_and_emulators_skip_a_busy_build_lock(
    busy: dict[str, str], argv: list[str]
) -> None:
    assert _wrap(argv, busy, 3) == f"{' '.join(argv)} held=0\n"


@pytest.mark.parametrize(
    "argv",
    [
        ["pnpm", "exec", "vite", "build"],
        ["pnpm", "exec", "astro", "build"],
        ["pnpm", "astro", "check"],
        ["vite", "build"],
        ["java", "-jar", "/x/bundletool.jar", "build-apks"],
        ["java", "-cp", "emulator.jar", "Main"],
        ["pnpm", "exec", "firebase", "emulators:exec", "pnpm test"],
        ["pnpm", "add", "serve"],
        ["cargo", "build", "--profile", "dev"],
        ["pnpm", "run", "build"],
    ],
)
def test_t2516_builds_still_wait_for_the_lock(busy: dict[str, str], argv: list[str]) -> None:
    """The first stderr line is the wait line: no timeout to sit out (a build that ran would exit)."""
    wrapper = str(buildlock.root() / buildlock.WRAPPER)
    with subprocess.Popen([wrapper, *argv], env=busy, stderr=subprocess.PIPE, text=True) as proc:
        assert proc.stderr is not None
        try:
            assert proc.stderr.readline().startswith("waiting for build lock held by card-x (godot")
        finally:
            proc.kill()


def _holder_seen(fakebin: Path, cwd: Path) -> str:
    """Run a fake build with no card from `cwd`; return the holder line it saw while it held the lock."""
    base = buildlock.root()
    buildlock.ensure(base)
    executable(fakebin / "cargo", f'#!/bin/bash\ncat "{base / buildlock.HOLDER}"\n')
    cwd.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k != buildlock.CARD_VAR}
    env.update(PATH=f"{fakebin}:{os.environ['PATH']}", PWD=str(cwd))
    return _wrap(["cargo", "build"], env, 10, cwd)


def test_t2516_a_holder_with_no_card_is_named_by_its_repo(fakebin: Path, tmp_path: Path) -> None:
    repo = tmp_path / "src" / "signal-bot"
    (repo / ".git").mkdir(parents=True)
    assert _holder_seen(fakebin, repo / "server" / "x").startswith("signal-bot (cargo build) since ")
    wt = repo / ".claude" / "worktrees" / "agent-1"
    (wt / ".git").parent.mkdir(parents=True)
    (wt / ".git").write_text("gitdir: elsewhere\n")
    assert _holder_seen(fakebin, wt / "lib").startswith("signal-bot (cargo build) ")


def test_t2516_a_holder_with_no_card_in_a_board_worktree_is_named_by_its_card(
    fakebin: Path, tmp_path: Path
) -> None:
    base = buildlock.root()
    assert _holder_seen(fakebin, base / "abcd1234-0" / "wt" / "web").startswith("abcd1234-0 (cargo build) ")
    child = base / "abcd1234-0" / "children" / "abcd1234-3" / "wt"
    assert _holder_seen(fakebin, child).startswith("abcd1234-3 (cargo build) ")
    assert _holder_seen(fakebin, base).startswith("? (cargo build) ")
    assert _holder_seen(fakebin, tmp_path / "nowhere").startswith("? (cargo build) ")


def test_t2516_a_card_less_ticket_of_an_older_wrapper_is_still_named_by_its_run_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An older wrapper writes `?`: the hold ceiling still reads its cwd (the new one names the card)."""
    base = buildlock.root()
    proc = tmp_path / "proc" / "42"
    proc.mkdir(parents=True)
    (proc / "cwd").symlink_to(base / "c2-0" / "wt")
    monkeypatch.setattr(holdceiling, "PROC", tmp_path / "proc")
    assert holdceiling._card(buildqueue.Ticket(1, 42, "held", "?", "cmake", "t"), base) == "c2-0"
