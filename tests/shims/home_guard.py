"""Catch any test that writes under kuhy's real HOME (T2612), however it built the path.

The temp HOME fixture covers code that calls `Path.home()` at call time; a module constant resolved at
import still points at the real HOME. An audit hook sees every write-mode open, delete, rename and mkdir
this process makes, so a write there fails the test that made it. The repo's own dir (and its parent, the
board run dir that holds coverage files) and the venv stay writable. Subprocesses get the temp HOME by env.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

REAL_HOME = str(Path.home())
EVENTS = frozenset(
    {"os.remove", "os.rename", "os.rmdir", "os.mkdir", "shutil.rmtree", "os.truncate", "os.symlink"}
)
WRITE_FLAGS = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND
_allowed: list[str] = []
_seen: list[str] = []


def writes(event: str, args: tuple[object, ...]) -> bool:
    """Tell whether this audit event writes to the file system."""
    if event == "open":
        mode, flags = args[1], args[2]
        return (
            any(c in mode for c in "wax+")
            if isinstance(mode, str)
            else isinstance(flags, int) and bool(flags & WRITE_FLAGS)
        )
    return event in EVENTS or event == "sqlite3.connect"


def under_real_home(target: object) -> str | None:
    """Return the absolute path if `target` names a path under the real HOME outside the allowed roots."""
    if not isinstance(target, (str, os.PathLike)):
        return None
    path = os.path.normpath(Path(os.fspath(target)).absolute())
    if not isinstance(path, str) or not path.startswith(f"{REAL_HOME}/"):
        return None
    return None if any(path == root or path.startswith(f"{root}/") for root in _allowed) else path


def targets(event: str, args: tuple[object, ...]) -> tuple[object, ...]:
    """Return the paths an event writes: a rename both ends, a symlink its link (not what it points at)."""
    return {"os.rename": args[:2], "os.symlink": args[1:2]}.get(event, args[:1])


def hook(event: str, args: tuple[object, ...]) -> None:
    """Record a write under the real HOME; never raise (an audit hook that raises breaks the caller)."""
    if (event == "open" or event in EVENTS or event == "sqlite3.connect") and args and writes(event, args):
        _seen.extend(f"{event} {hit}" for target in targets(event, args) if (hit := under_real_home(target)))


def install(*allowed: Path) -> None:
    """Allow writes under `allowed` (and the venv), then start watching."""
    _allowed.extend(str(root.resolve()) for root in (*allowed, Path(sys.prefix)))
    sys.addaudithook(hook)


def take() -> list[str]:
    """Return and clear the writes seen since the last call."""
    seen = list(_seen)
    _seen.clear()
    return seen
