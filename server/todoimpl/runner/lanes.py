"""Two lanes for the board's own checks: a light one for linters, the machine-wide build lock for builds.

A pre-commit run of ruff, mypy and a file-length script waited 20-100 min behind other cards' flutter and
gradle builds on the one build lock (analysis of 2026-11-19: 577 idle minutes between turns). A command is
`light` only when every part of it is a positively known linter; anything unknown is `heavy` and takes the
build lock as before. A light check takes the light slot instead: one slot machine-wide, so a check wrongly
called light still adds at most one extra build next to the one heavy build. Both run under capped.sh.
"""

from __future__ import annotations

import contextlib
import fcntl
import os
import re
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from typing import IO, TYPE_CHECKING

from todoimpl import atomic

from . import bgwait, buildlock, stepwatch

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

HEAVY = "heavy"
LIGHT = "light"
LIGHT_LOCK = "light.lock"
LIGHT_HOLDER = "light.lock.holder"
# Programs that only read the tree and report: linters, formatters in check mode, type checkers, git.
LIGHT_TOOLS = frozenset(
    shlex.split(
        "ruff mypy pyright shellcheck shfmt black isort flake8 pylint bandit codespell yamllint actionlint"
        " markdownlint eslint prettier git head tail grep wc sort cat"
    )
)
WRAPPERS = frozenset({"capped.sh", "nice", "ionice", "env", "timeout", "uv", "python", "python3"})
SEPARATORS = frozenset({";", "&&", "||", "|"})
REDIRECT = re.compile(r"^(?:[<>][<>&]*|&[<>&]+)$")  # not a lone `&`: that is a background job
ASSIGNMENT = re.compile(r"^[A-Za-z_]\w*=")
TOOL_WORDS = (
    r"flutter|dart|gradlew?|java|mvn|pnpm|npm|npx|yarn|vite|vitest|jest|cargo|rustc|go|make|cmake|ninja|godot"
    r"|pytest|uv|tsc|node|astro|webpack|docker|xcodebuild"
)
HEAVY_WORD = re.compile(rf"\b(?:{TOOL_WORDS})\b", re.IGNORECASE)
HEAVY_HOOK = re.compile(rf"\b(?:{TOOL_WORDS}|build|builds|test|tests)\b", re.IGNORECASE)
HOOK_FIELD = re.compile(r"^\s*(?:-\s+)?(?:id|name|entry|language):\s*(?P<value>.*)$")
SCRIPT_CAP = 64_000
PRE_COMMIT = ".pre-commit-config.yaml"


def _script_light(path: Path) -> bool:
    """Say whether a repo script mentions no build tool (comments aside); unreadable or large is heavy."""
    try:
        if path.stat().st_size > SCRIPT_CAP:
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    body = "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))
    return HEAVY_WORD.search(body) is None


def _hook_entry_light(entry: str, cwd: Path) -> bool:
    """Say whether a hook's entry names no build tool and runs only light repo scripts."""
    if HEAVY_HOOK.search(entry):
        return False
    try:
        words = shlex.split(entry)
    except ValueError:
        return False
    return all(_script_light(cwd / w) for w in words if (cwd / w).is_file())


def precommit_light(cwd: Path) -> bool:
    """Say whether no hook of the repo's pre-commit config builds or tests (no config: not light)."""
    try:
        text = (cwd / PRE_COMMIT).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    for line in text.splitlines():
        found = HOOK_FIELD.match(line)
        if found and not _hook_entry_light(found["value"].split(" #")[0].strip(), cwd):
            return False
    return True


def _unassigned(words: list[str]) -> list[str]:
    """Drop the leading `VAR=value` words of a command."""
    skip = 0
    while skip < len(words) and ASSIGNMENT.match(words[skip]):
        skip += 1
    return words[skip:]


def _program(words: list[str]) -> str:
    """Return the program a segment runs, wrappers (`timeout 50`, `uv run --frozen`, `python -m`) peeled."""
    words = _unassigned(words)
    while words and (wrapper := Path(words[0]).name) in WRAPPERS:
        rest = words[1:]
        if wrapper == "timeout":
            rest = rest[1:]  # its duration
        elif wrapper in {"python", "python3"}:
            if rest[:1] != ["-m"]:
                break  # a script: unknown
            rest = rest[1:]
        else:
            if wrapper == "uv":
                if rest[:1] != ["run"]:
                    break  # uv sync, uv pip, ...: unknown
                rest = rest[1:]
            while rest and rest[0].startswith("-"):
                rest = rest[1:]
        words = _unassigned(rest)
    return Path(words[0]).name if words else ""


def _segments(command: str) -> list[list[str]] | None:
    """Split a command on `;`, `&&`, `||` and `|`; None when it has anything a parser should not guess at."""
    if "\n" in command or "`" in command or "$(" in command:
        return None
    lex = shlex.shlex(command, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        tokens = list(lex)
    except ValueError:
        return None
    segments: list[list[str]] = [[]]
    for token in tokens:
        if token in SEPARATORS:
            segments.append([])
        elif REDIRECT.match(token):
            segments[-1].append("")  # a redirection: its target is no program
        elif set(token) <= set("();<>|&"):
            return None  # a subshell, a group, a background job
        else:
            segments[-1].append(token)
    return segments


def classify(command: str, cwd: Path) -> str:
    """Return `light` when every part of the command is a known linter, else `heavy` (the safe default)."""
    segments = _segments(command)
    if not segments:
        return HEAVY
    for words in segments:
        prog = _program([w for w in words if w])
        if prog == "pre-commit":
            if not precommit_light(cwd):
                return HEAVY
        elif prog not in LIGHT_TOOLS:
            return HEAVY
    return LIGHT


def _holder_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def light_holder() -> tuple[str, float | None]:
    """Return who holds the light slot (its card, or its command for a card-less check) and since when."""
    found = bgwait.HELD.fullmatch(_holder_text(buildlock.root() / LIGHT_HOLDER))
    if found is None:
        return "?", None
    who = found["card"] if found["card"] != "?" else found["cmd"]
    return who, time.mktime(time.strptime(found["at"], "%Y-%m-%d %H:%M:%S"))


@contextlib.contextmanager
def light_slot(
    card: str, command: str, out: IO[str] | int, on_wait: Callable[[], None] | None = None
) -> Iterator[None]:
    """Hold the one light slot, waiting for it (said once in `out`); a no-op under a held build lock."""
    if os.environ.get(buildlock.HELD_VAR) == "1":
        yield
        return
    base = buildlock.root()
    base.mkdir(parents=True, exist_ok=True)
    holder = base / LIGHT_HOLDER
    with (base / LIGHT_LOCK).open("a", encoding="utf-8") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            if not isinstance(out, int):
                out.write(f"waiting for light slot held by {_holder_text(holder) or 'another check'}\n")
                out.flush()
            if on_wait is not None:
                on_wait()
            fcntl.flock(lock, fcntl.LOCK_EX)
        since = time.strftime("%Y-%m-%d %H:%M:%S")
        atomic.write_text(holder, f"{card} ({command[:120]}) since {since}\n", durable=False)
        try:
            yield
        finally:
            holder.write_text("", encoding="utf-8")


@dataclass
class Timing:
    """What one check learned about its wait: its lane, seconds queued and run, and who it queued behind."""

    lane: str = HEAVY
    queue_s: float = 0.0
    run_s: float = 0.0
    holder: str = ""


@contextlib.contextmanager
def admitted(
    command: str, cwd: Path, card: str, out: IO[str] | int, timing: Timing | None = None
) -> Iterator[None]:
    """Wait for the command's lane, then yield; fill `timing` and show the wait on the card (T2185)."""
    timing = timing if timing is not None else Timing()
    timing.lane = classify(command, cwd)
    heavy = timing.lane == HEAVY
    lock = buildlock.root() / (buildlock.LOCK if heavy else LIGHT_LOCK)
    watch, key = stepwatch.current(), id(timing)

    def waiting() -> None:  # the lock is taken: name its holder on the card, the idle-turn line (T2124)
        who, since = bgwait.holder(lock) if heavy else light_holder()
        timing.holder = who
        if watch is not None:
            watch.queued(key, {"lock": True, "who": who, "since": since or time.time()})

    gate = buildlock.held(card, command, out, waiting) if heavy else light_slot(card, command, out, waiting)
    began = time.monotonic()
    try:
        with gate:
            took = time.monotonic()
            timing.queue_s = took - began
            if watch is not None:
                watch.started(key)
            try:
                yield
            finally:
                timing.run_s = time.monotonic() - took
    finally:
        if watch is not None:
            watch.started(key)
