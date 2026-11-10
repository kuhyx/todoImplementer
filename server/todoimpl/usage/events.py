"""Tolerant readers for a run's `*.stream.jsonl` files (claude -p --output-format stream-json)."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from pathlib import Path

MEMO_MAX = 8192
_MEMO: dict[tuple[str, Path], tuple[tuple[int, int], Any]] = {}


def per_file[T](tag: str, path: Path, fold: Callable[[Path], T]) -> T:
    """Return `fold(path)`, recomputed only when the file's mtime or size changed (T1910).

    /api/usage folds every stream of every run; a finished stream never changes, so it is read once.
    Callers must keep `fold` pure and its result immutable.
    """
    info = path.stat()
    sig = (info.st_mtime_ns, info.st_size)
    hit = _MEMO.get((tag, path))
    if hit is not None and hit[0] == sig:
        return hit[1]  # type: ignore[no-any-return]
    if len(_MEMO) >= MEMO_MAX:  # runs come and go: never grow without bound
        _MEMO.clear()
    value = fold(path)
    _MEMO[tag, path] = (sig, value)
    return value


def stream_files(run_dir: Path) -> list[Path]:
    """Stream files of one run, name-sorted (plan before implement is not implied)."""
    return sorted(run_dir.glob("*.stream.jsonl"))


def iter_events(path: Path) -> Iterator[dict[str, Any]]:
    """Yield every JSON-object line; blank, torn or non-object lines are skipped.

    A live session appends to the file, so the last line may be half-written.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            yield obj
