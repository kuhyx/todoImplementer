"""One build at a time across every board session and check (DOCS-turns.md, "One build at a time").

~25 sessions building at once froze kuhy's PC (2026-11-11). The lock is `<root>/build.lock` (flock). Turns
get it through one-line shims in `<root>/shims` that run `<root>/buildlock.sh <tool>`; the server's own
checks take it in `held` before their timeout starts, so a queued check never times out while it waits.
A PATH prefix in the turn env does not reach claude's Bash tool (kuhy's zshrc puts ~/.local/bin first), so
the shim dir goes in through `CLAUDE_ENV_FILE`, which claude sources before every Bash command.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import shlex
import time
from pathlib import Path
from typing import IO, TYPE_CHECKING

from todoimpl import atomic
from todoimpl.board import state as store

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

ROOT_VAR = "TODOIMPL_BUILD_ROOT"  # tests point it at a temp dir; unset, the lock lives in the run root
HELD_VAR = "TODOIMPL_BUILD_LOCK_HELD"  # set under a held lock: nested tools run straight away
CARD_VAR = "TODOIMPL_BUILD_CARD"
LOCK = "build.lock"
HOLDER = "build.lock.holder"
WRAPPER = "buildlock.sh"
SHIM_DIR = "shims"
ENV_DIR = "shims-env"
# Real build tools only. Never node, npx, uvx, git, python or claude: MCP servers and claude itself use them.
TOOLS = (
    "flutter", "dart", "gradle", "java", "pnpm", "npm", "yarn", "vite", "vitest", "cargo", "go", "make",
    "cmake", "ninja", "godot", "pytest", "uv",
)  # fmt: skip
# Build tuning for every turn: no Gradle daemon left behind, bounded workers and heap, four cargo jobs.
TUNING = {
    "GRADLE_OPTS": "-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=4 -Dorg.gradle.jvmargs=-Xmx3g",
    "CARGO_BUILD_JOBS": "4",
}
WAITING = "waiting for build lock held by {held}\n"


def root() -> Path:
    """Return the dir of the lock, the wrapper and the shims: `$TODOIMPL_BUILD_ROOT`, else the run root."""
    found = os.environ.get(ROOT_VAR)
    return Path(found) if found else store.run_root()


def _put(path: Path, text: str, mode: int) -> None:
    """Write `path` only when it differs: running turns exec these files while a new turn starts."""
    if _read(path) != text.strip():
        atomic.write_text(path, text, durable=False, mode=mode)


def ensure(base: Path) -> Path:
    """Write the wrapper and one shim per tool under `base`; return the shim dir."""
    wrapper = base / WRAPPER
    _put(wrapper, Path(__file__).with_name(WRAPPER).read_text(encoding="utf-8"), 0o755)
    shims = base / SHIM_DIR
    for tool in TOOLS:
        _put(shims / tool, f'#!/bin/bash\nexec {shlex.quote(str(wrapper))} {tool} "$@"\n', 0o755)
    return shims


def turn_env(card: str) -> dict[str, str]:
    """Return the env a turn adds: its env file (shims first on PATH), its card and the build tuning."""
    base = root()
    shims = shlex.quote(str(ensure(base)))
    env_file = base / ENV_DIR / f"{card}.sh"
    _put(env_file, f'[[ "$PATH" == {shims}:* ]] || export PATH={shims}:"$PATH"\n', 0o644)
    return {"CLAUDE_ENV_FILE": str(env_file), CARD_VAR: card, **TUNING}


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def _say(out: IO[str] | int, text: str) -> None:
    if not isinstance(out, int):
        out.write(text)
        out.flush()


@contextlib.contextmanager
def held(
    card: str, command: str, out: IO[str] | int, on_wait: Callable[[], None] | None = None
) -> Iterator[None]:
    """Hold the build lock, waiting for it (said once in `out`, `on_wait` called); a no-op when held."""
    if os.environ.get(HELD_VAR) == "1":
        yield
        return
    base = root()
    base.mkdir(parents=True, exist_ok=True)
    holder = base / HOLDER
    with (base / LOCK).open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            _say(out, WAITING.format(held=_read(holder) or "another build"))
            if on_wait is not None:
                on_wait()
            fcntl.flock(lock, fcntl.LOCK_EX)
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        atomic.write_text(holder, f"{card} ({command[:120]}) since {since}\n", durable=False)
        try:
            yield
        finally:
            holder.write_text("", encoding="utf-8")
