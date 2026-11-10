"""Draft a lesson from a gate rejection with a one-shot haiku call."""

from __future__ import annotations

import hashlib
import json
import os
from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any

from todoimpl.board.state import run_root
from todoimpl.lessons.store import LOCK, Lesson, LessonError, load_lessons, save_lessons
from todoimpl.runner import oneshot
from todoimpl.runner.files import root_of

if TYPE_CHECKING:
    from collections.abc import Callable

Drafter = "Callable[[str], str]"
CLAUDE_TIMEOUT_S = 50.0  # under the 60 s per-action cap
FIELDS = ("skill", "mistake", "rule", "evidence")
PROMPT = """override
You turn a rejected change into one reusable lesson for a Claude Code skill.
Rejection note from the reviewer:
{note}

Skills this run loaded: {loaded}
Skills you may pick: {allowed}

Reply with ONLY a JSON object with string fields:
"skill" (exactly one of the skills you may pick), "mistake" (what went wrong, one sentence),
"rule" (an imperative rule that prevents it, one sentence), "evidence" (the concrete proof from the note).
"""


def build_skills() -> list[str]:
    """Names of installed build-* skills (dirs with a SKILL.md), same root skill_lesson.py uses."""
    root = Path(os.environ.get("PROGRAM_SKILLS_DIR") or Path.home() / ".claude/skills")
    return sorted(p.parent.name for p in root.glob("build-*/SKILL.md"))


def claude_drafter(prompt: str, root: Path | None = None) -> str:
    """Default drafter: the narrow Haiku one-shot (`runner/oneshot.py`); its usage goes to the root ledger."""
    return oneshot.run(
        prompt,
        model="haiku",
        kind="lesson",
        root=root or run_root(),
        timeout=CLAUDE_TIMEOUT_S,
        error=LessonError,
    )


def parse_draft(text: str, allowed: list[str]) -> dict[str, str]:
    """Pull the JSON object out of the model text; validate fields and the skill choice."""
    start, end = text.find("{"), text.rfind("}")
    try:
        data: Any = json.loads(text[start : end + 1]) if 0 <= start < end else None
    except ValueError:
        data = None
    if not isinstance(data, dict) or not all(
        isinstance(data.get(k), str) and data[k].strip() for k in FIELDS
    ):
        msg = f"draft is not a JSON object with {', '.join(FIELDS)}: {text[:200]!r}"
        raise LessonError(msg)
    if data["skill"] not in allowed:
        msg = f"draft picked unknown skill {data['skill']!r}; allowed: {', '.join(allowed)}"
        raise LessonError(msg)
    return {k: data[k].strip() for k in FIELDS}


def draft_lesson(
    run_dir: Path, rejection_note: str, skills: list[str], drafter: Callable[[str], str] | None = None
) -> Lesson:
    """Draft a lesson from a gate rejection and store it in `<run_dir>/lessons.json`.

    The skill is one of the run's loaded `skills` or an installed build-* skill.
    Nothing touches a skill file here; that is `approve`. Re-drafting identical
    content returns the stored lesson (and its state) instead of adding a copy.
    """
    allowed = list(dict.fromkeys([*skills, *build_skills()]))
    prompt = PROMPT.format(
        note=rejection_note.strip(), loaded=", ".join(skills) or "none", allowed=", ".join(allowed)
    )
    fields = parse_draft((drafter or partial(claude_drafter, root=root_of(run_dir)))(prompt), allowed)
    digest = hashlib.sha256("\0".join(fields.values()).encode()).hexdigest()[:10]
    with LOCK:
        lessons = load_lessons(run_dir)
        known = next((x for x in lessons if x.id == digest), None)
        if known:
            return known
        lesson = Lesson(digest, fields["skill"], fields["mistake"], fields["rule"], fields["evidence"])
        save_lessons(run_dir, [*lessons, lesson])
    return lesson
