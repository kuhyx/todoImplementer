"""Lesson records kept in `<run_dir>/lessons.json` (shape: contracts/common.schema.json#/$defs/lesson)."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Literal

from todoimpl import atomic

if TYPE_CHECKING:
    from pathlib import Path

LESSONS_FILE = "lessons.json"
# One process-wide lock: the HTTP server is threaded and every write is read-modify-write.
LOCK = threading.RLock()


class LessonError(Exception):
    """A lesson could not be drafted, loaded or recorded."""


@dataclass(frozen=True)
class Lesson:
    """A drafted lesson; it reaches a skill only once `state` is approved."""

    id: str
    skill: str
    mistake: str
    rule: str
    evidence: str
    state: Literal["drafted", "approved", "rejected"] = "drafted"

    def to_dict(self) -> dict[str, str]:
        """JSON-ready dict, exactly the contract's lesson object."""
        return asdict(self)


def load_lessons(run_dir: Path) -> list[Lesson]:
    """All lessons of a run, oldest first; a corrupt file raises instead of reading as empty."""
    path = run_dir / LESSONS_FILE
    if not path.exists():
        return []
    try:
        return [Lesson(**item) for item in json.loads(path.read_text(encoding="utf-8"))["lessons"]]
    except (OSError, ValueError, TypeError, KeyError) as exc:
        msg = f"corrupt {path}: {exc}"
        raise LessonError(msg) from exc


def latest_lesson(run_dir: Path) -> Lesson | None:
    """Return the lesson the drawer shows: the newest one, if any."""
    lessons = load_lessons(run_dir)
    return lessons[-1] if lessons else None


def save_lessons(run_dir: Path, lessons: list[Lesson]) -> None:
    """Atomic rewrite (tmp + replace) so readers never see a torn file."""
    path = run_dir / LESSONS_FILE
    atomic.write_text(path, json.dumps({"lessons": [x.to_dict() for x in lessons]}, indent=2) + "\n")
