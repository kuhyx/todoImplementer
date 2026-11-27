"""Three builds at a time across every board session and check (DOCS-turns.md, "Three builds at a time").

~25 sessions building at once froze kuhy's PC (2026-11-11), so one build ran at a time; heavy builds then
queued 4-6 deep, and kuhy picked three at once on 2026-11-21 (each card is capped at 10 GiB, the board at
18 GiB, T2405). The lock is `SLOTS` flock files, `<root>/build.lock` and `build.lock.<n>`, each with its
`<lock>.holder`, taken in arrival order through the ticket queue (buildqueue.py, T2164, T2419). Turns
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

from . import buildqueue, cardslice

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

ROOT_VAR = "TODOIMPL_BUILD_ROOT"  # tests point it at a temp dir; unset, the lock lives in the run root
HELD_VAR = "TODOIMPL_BUILD_LOCK_HELD"  # set under a held lock: nested tools run straight away
CARD_VAR = "TODOIMPL_BUILD_CARD"
LOCK = "build.lock"
HOLDER = "build.lock.holder"
SLOTS = 3  # kuhy, 2026-11-21: three builds at once (was one, 2026-11-11)
SLOTS_VAR = "TODOIMPL_BUILD_SLOTS"  # tests pin it; the wrapper reads it too
SLOTS_MARK = "@SLOTS@"
WRAPPER = "buildlock.sh"
QUEUE_LIB = "buildlock_queue.sh"  # the wrapper sources it; written first: a new wrapper never sees an old one
SHIM_DIR = "shims"
ENV_DIR = "shims-env"
# Real build tools only (`fvm` runs its pinned flutter by path: unshimmed it dodged the lock, T2488).
# Never node, npx, uvx, git, python or claude: MCP servers and claude itself use them.
TOOLS = (
    "flutter", "dart", "gradle", "java", "pnpm", "npm", "yarn", "vite", "vitest", "cargo", "go", "cmake",
    "ninja", "godot", "pytest", "uv", "pre-commit", "fvm",
)  # fmt: skip
# `make` is no shim (T2415): a gate step like `make lint` did 0.04 s of work but queued minutes behind other
# cards' builds; each heavy tool its recipes run (uv, pnpm, cargo) locks itself. A plain make+gcc build runs
# unlocked. `uv run <linter>` skips the lock too: it only reads the tree. Shared with lanes.py.
LINTERS = frozenset(
    shlex.split(
        "ruff mypy pyright shellcheck shfmt black isort flake8 pylint bandit codespell yamllint actionlint"
        " markdownlint eslint prettier coverage"  # coverage combine/report only read data files (T2423)
    )
)
LINTERS_MARK = "@LINTERS@"
# Guard shims: `flock` on the build lock, its holder or its queue is refused (it would jump the queue, T2167).
GUARDS = ("flock",)
# Wait shims: a long `timeout` around a waiter and a following `tail` end after 40 s (T2591, waitshim.sh).
WAITS = ("timeout", "tail")
WAIT_SOURCE = "waitshim.sh"
# Build tuning for every turn: no Gradle daemon left behind, bounded workers and heap, four cargo jobs.
TUNING = {
    "GRADLE_OPTS": "-Dorg.gradle.daemon=false -Dorg.gradle.workers.max=4 -Dorg.gradle.jvmargs=-Xmx3g",
    "CARGO_BUILD_JOBS": "4",
}
WAITING = "waiting for build lock held by {held}; {ahead} ahead\n"


def root() -> Path:
    """Return the dir of the lock, the wrapper and the shims: `$TODOIMPL_BUILD_ROOT`, else the run root."""
    found = os.environ.get(ROOT_VAR)
    return Path(found) if found else store.run_root()


def _put(path: Path, text: str, mode: int) -> None:
    """Write `path` only when it differs: running turns exec these files while a new turn starts."""
    if _read(path) != text.strip():
        atomic.write_text(path, text, durable=False, mode=mode)


def ensure(base: Path) -> Path:
    """Write the wrapper, its queue lib and one shim per tool under `base`; return the shim dir."""
    wrapper = base / WRAPPER
    _put(base / QUEUE_LIB, Path(__file__).with_name(QUEUE_LIB).read_text(encoding="utf-8"), 0o644)
    source = Path(__file__).with_name(WRAPPER).read_text(encoding="utf-8")
    source = source.replace(LINTERS_MARK, " ".join(sorted(LINTERS))).replace(SLOTS_MARK, str(SLOTS))
    _put(wrapper, source, 0o755)
    shims = base / SHIM_DIR
    keep = {*TOOLS, *GUARDS, *WAITS, cardslice.SHIM}
    if shims.is_dir():  # a tool that left TOOLS (make, T2415) must stop locking in the running sessions too
        for stale in shims.iterdir():
            if stale.name not in keep:
                stale.unlink(missing_ok=True)
    for tool in TOOLS:
        _put(shims / tool, f'#!/bin/bash\nexec {shlex.quote(str(wrapper))} {tool} "$@"\n', 0o755)
    for tool in GUARDS:
        _put(shims / tool, f'#!/bin/bash\nexec {shlex.quote(str(wrapper))} --{tool} "$@"\n', 0o755)
    # A session's board-slice job joins its card's slice (cardslice.py, T2401).
    shim = Path(__file__).with_name(cardslice.SHIM_SOURCE).read_text(encoding="utf-8")
    _put(shims / cardslice.SHIM, shim, 0o755)
    waits = Path(__file__).with_name(WAIT_SOURCE).read_text(encoding="utf-8")
    for tool in WAITS:
        _put(shims / tool, waits, 0o755)
    return shims


def turn_env(card: str) -> dict[str, str]:
    """Return the env a turn adds: its env file (shims first on PATH), its card and the build tuning."""
    base = root()
    shims = shlex.quote(str(ensure(base)))
    env_file = base / ENV_DIR / f"{card}.sh"
    _put(env_file, f'[[ "$PATH" == {shims}:* ]] || export PATH={shims}:"$PATH"\n', 0o644)
    own = {cardslice.SLICE_VAR: cardslice.card_slice(card)}
    return {"CLAUDE_ENV_FILE": str(env_file), CARD_VAR: card, **own, **TUNING}


def slots() -> int:
    """Return how many builds may run at once: `$TODOIMPL_BUILD_SLOTS`, else `SLOTS` (at least one)."""
    found = os.environ.get(SLOTS_VAR, "")
    return max(int(found), 1) if found.isdigit() else SLOTS


def slot_lock(base: Path, n: int) -> Path:
    """Return slot `n`'s lock file: `build.lock` for slot 0 (old wrappers take it), `build.lock.<n>` after."""
    return base / (LOCK if n == 0 else f"{LOCK}.{n}")


def holder_of(lock: Path) -> Path:
    """Return the holder file of a slot lock: `<lock>.holder`."""
    return lock.with_name(f"{lock.name}.holder")


def holders(base: Path) -> str:
    """Return who holds the slots, longest-held first, joined by ` + ` ("" when none)."""
    found = [_read(holder_of(slot_lock(base, n))) for n in range(slots())]
    return " + ".join(sorted((h for h in found if h), key=lambda h: h.rpartition(" since ")[2]))


def _take_slot(base: Path, wait: Callable[[int], None]) -> IO[str]:
    """Take a free slot's lock; when all are busy (an old wrapper, a hand-held lock) wait on slot 0."""
    while True:
        for n in range(slots()):
            fh = slot_lock(base, n).open("a", encoding="utf-8")
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                fh.close()
                continue
            return fh
        wait(0)
        fh = slot_lock(base, 0).open("a", encoding="utf-8")
        if buildqueue.lock_within(fh, None if slots() == 1 else buildqueue.RECHECK):
            return fh
        fh.close()


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
    """Hold the build lock in queue order; a wait is said once in `out` and calls `on_wait`; held: a no-op."""
    if os.environ.get(HELD_VAR) == "1":
        yield
        return
    base = root()
    base.mkdir(parents=True, exist_ok=True)
    said: list[int] = []

    def wait(ahead: int) -> None:
        if not said:
            said.append(ahead)
            _say(out, WAITING.format(held=holders(base) or "another build", ahead=ahead))
            if on_wait is not None:
                on_wait()

    with buildqueue.queued(base, card, command, wait, slots()) as mark, _take_slot(base, wait) as lock:
        holder = holder_of(Path(lock.name))
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        atomic.write_text(holder, f"{card} ({command[:120]}) since {since}\n", durable=False)
        mark()
        try:
            yield
        finally:
            holder.write_text("", encoding="utf-8")
