"""Which skills a run loaded: Skill tool_use events in its stream-json files."""

from __future__ import annotations

from typing import TYPE_CHECKING

from todoimpl.usage.events import iter_events, stream_files

if TYPE_CHECKING:
    from pathlib import Path


CACHE_MAX = 4096
_CACHE: dict[Path, tuple[int, int, list[str]]] = {}


def skills_loaded(stream_path: Path) -> list[str]:
    """Ordered, de-duplicated `input.skill` of every Skill tool_use in one stream file.

    Cached per (mtime, size): the board asks for every run on each request; a finished stream never changes.
    """
    try:
        info = stream_path.stat()
    except OSError:
        return []
    key = (info.st_mtime_ns, info.st_size)
    hit = _CACHE.get(stream_path)
    if hit is not None and hit[:2] == key:
        return list(hit[2])
    names = _parse(stream_path)
    if len(_CACHE) >= CACHE_MAX:  # runs come and go; never grow without bound
        _CACHE.clear()
    _CACHE[stream_path] = (*key, names)
    return list(names)


def _parse(stream_path: Path) -> list[str]:
    found: dict[str, None] = {}
    for event in iter_events(stream_path):
        message = event.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        for block in content if isinstance(content, list) else []:
            if not (
                isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "Skill"
            ):
                continue
            args = block.get("input")
            name = args.get("skill") if isinstance(args, dict) else None
            if isinstance(name, str) and name:
                found.setdefault(name)
    return list(found)


def run_skills(run_dir: Path) -> list[str]:
    """Skills loaded across all streams of a run (plan, implement, review, ...), first use first."""
    merged: dict[str, None] = {}
    for stream in stream_files(run_dir):
        merged.update(dict.fromkeys(skills_loaded(stream)))
    return list(merged)
